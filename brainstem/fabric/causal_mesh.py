"""Bilateral causal settlement records and locally verifiable equivocation evidence.

A bilateral signature is not regulatory settlement, consensus, or proof of
economic value. The chain is a two-party signed append-only transcript.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator

GENESIS_HASH = "0" * 64
MAX_ENERGY_NANOJOULES = 10**21


def canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def energy_to_nanojoules(value: float) -> int:
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("settled energy must be finite and nonnegative")
    try:
        exact = Decimal(str(value)) * Decimal(1_000_000_000)
    except InvalidOperation as exc:
        raise ValueError("invalid energy") from exc
    if exact != exact.to_integral_value() or exact > MAX_ENERGY_NANOJOULES:
        raise ValueError("energy must be representable in nanjoules within bounds")
    return int(exact)


class BilateralEntanglementRecord(BaseModel):
    """One co-signed, sequential ledger entry; no independent value attestation."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: UUID
    seq_no: int = Field(ge=1)
    initiator_pub_hex: str = Field(pattern=r"^[a-f0-9]{64}$")
    counterparty_pub_hex: str = Field(pattern=r"^[a-f0-9]{64}$")
    initiator_prev_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    counterparty_prev_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    poecl_receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    value_delta_micro_units: int
    joules_settled: float = Field(ge=0.0, allow_inf_nan=False)
    timestamp_utc: datetime
    initiator_sig_hex: str = Field(pattern=r"^[a-f0-9]{128}$")
    counterparty_sig_hex: str = Field(pattern=r"^[a-f0-9]{128}$")

    @model_validator(mode="after")
    def validate_record(self) -> "BilateralEntanglementRecord":
        if self.initiator_pub_hex == self.counterparty_pub_hex:
            raise ValueError("bilateral record requires two distinct signing keys")
        if self.timestamp_utc.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.initiator_prev_hash != self.counterparty_prev_hash:
            raise ValueError("bilateral predecessor heads disagree")
        energy_to_nanojoules(self.joules_settled)
        return self

    @property
    def energy_nanojoules(self) -> int:
        return energy_to_nanojoules(self.joules_settled)

    def signing_payload(self) -> bytes:
        return canonical_json({
            "record_id": str(self.record_id),
            "seq_no": self.seq_no,
            "initiator_pub_hex": self.initiator_pub_hex,
            "counterparty_pub_hex": self.counterparty_pub_hex,
            "initiator_prev_hash": self.initiator_prev_hash,
            "counterparty_prev_hash": self.counterparty_prev_hash,
            "poecl_receipt_hash": self.poecl_receipt_hash,
            "value_delta_micro_units": self.value_delta_micro_units,
            "joules_settled": self.joules_settled,
            "timestamp_utc": self.timestamp_utc.astimezone(timezone.utc).isoformat(),
        })

    def verify_bilateral_signatures(self) -> bool:
        try:
            msg = self.signing_payload()
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(self.initiator_pub_hex)).verify(
                bytes.fromhex(self.initiator_sig_hex), msg
            )
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(self.counterparty_pub_hex)).verify(
                bytes.fromhex(self.counterparty_sig_hex), msg
            )
            return True
        except (ValueError, TypeError, Exception) as exc:
            # Signature rejection never exposes secret material.
            return False

    def commitment_hash(self) -> str:
        return sha256_hex(b"KINDRED-BILATERAL-RECORD-v1\x00" + canonical_json(self.model_dump(mode="json")))


class EquivocationFraudWarrant(BaseModel):
    """Third parties must inspect both fully signed conflicting records."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    seq_no: int
    prior: BilateralEntanglementRecord
    conflicting: BilateralEntanglementRecord

    def verify(self) -> bool:
        return (
            self.prior.seq_no == self.conflicting.seq_no == self.seq_no
            and self.prior.initiator_pub_hex == self.conflicting.initiator_pub_hex
            and self.prior.counterparty_pub_hex == self.conflicting.counterparty_pub_hex
            and self.prior.commitment_hash() != self.conflicting.commitment_hash()
            and self.prior.verify_bilateral_signatures()
            and self.conflicting.verify_bilateral_signatures()
        )


class CausalMeshNode:
    """Single-process peer ledger, not distributed consensus or banking settlement."""
    def __init__(self, private_key: Ed25519PrivateKey | None = None):
        self.private_key = private_key or Ed25519PrivateKey.generate()
        self.public_key_hex = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ).hex()
        self.chain_head = GENESIS_HASH
        self.next_seq_no = 1
        self._committed: dict[int, BilateralEntanglementRecord] = {}

    def sign_commitment(self, payload: bytes) -> str:
        return self.private_key.sign(payload).hex()

    def verify_and_commit(self, record: BilateralEntanglementRecord) -> BilateralEntanglementRecord | EquivocationFraudWarrant:
        if self.public_key_hex not in (record.initiator_pub_hex, record.counterparty_pub_hex):
            raise PermissionError("record does not involve this node")
        if not record.verify_bilateral_signatures():
            raise PermissionError("invalid bilateral settlement signatures")
        previous = self._committed.get(record.seq_no)
        if previous is not None:
            if previous.commitment_hash() == record.commitment_hash():
                return previous
            return EquivocationFraudWarrant(seq_no=record.seq_no, prior=previous, conflicting=record)
        if record.seq_no != self.next_seq_no:
            raise ValueError("nonconsecutive settlement sequence")
        predecessor = (
            record.initiator_prev_hash if self.public_key_hex == record.initiator_pub_hex
            else record.counterparty_prev_hash
        )
        if predecessor != self.chain_head:
            raise ValueError("invalid peer causal predecessor")
        self.chain_head = record.commitment_hash()
        self._committed[record.seq_no] = record
        self.next_seq_no += 1
        return record

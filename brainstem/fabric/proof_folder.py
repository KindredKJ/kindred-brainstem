"""Signed Merkle folding of already verified bilateral settlement transcripts.

This is *not* a zero-knowledge argument, a recursive SNARK/STARK, or a proof
that all underlying records satisfy an invariant. A trusted aggregator checks
the individual records and signs the aggregate claims. An edge verifier
authenticates that signed claim; a separate O(log N) membership witness
proves inclusion of one record in that claimed set.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from typing import Iterable, Sequence
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator

from brainstem.fabric.causal_mesh import (
    BilateralEntanglementRecord, GENESIS_HASH, canonical_json, sha256_hex,
)

FOLD_SCHEMA = "kindred.causal_mesh.signed_merkle_fold.v1"
MAX_FOLD_RECORDS = 2_000_000


def _require_hash(value: str) -> bytes:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("expected 32-byte lowercase hex digest")
    data = bytes.fromhex(value)
    if data.hex() != value:
        raise ValueError("hash must be lowercase hex")
    return data


def _hash_pair(left_hex: str, right_hex: str) -> str:
    return sha256_hex(b"\x01" + _require_hash(left_hex) + _require_hash(right_hex))


def _hash_leaf(value: str) -> str:
    return sha256_hex(b"\x00" + _require_hash(value))


def build_merkle_tree(raw_commitments: Sequence[str]) -> list[list[str]]:
    if not raw_commitments:
        raise ValueError("cannot build an empty Merkle tree")
    if len(raw_commitments) > MAX_FOLD_RECORDS:
        raise ValueError("batch exceeds maximum fold size")
    levels = [[_hash_leaf(item) for item in raw_commitments]]
    while len(levels[-1]) > 1:
        level = levels[-1]
        if len(level) % 2:
            level = level + [level[-1]]
        levels.append([
            _hash_pair(level[i], level[i + 1]) for i in range(0, len(level), 2)
        ])
    return levels


class MerkleInclusionProof(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    leaf_index: int = Field(ge=0)
    leaf_count: int = Field(ge=1)
    leaf_hash: str = Field(pattern=r"^[a-f0-9]{64}$")  # raw record commitment
    sibling_hashes: tuple[str, ...]
    sibling_is_right: tuple[bool, ...]
    expected_root: str = Field(pattern=r"^[a-f0-9]{64}$")

    def verify(self, *, leaf_hash: str, trusted_root: str) -> bool:
        """Caller supplies the actual record's hash and an anchored signed root."""
        try:
            if leaf_hash != self.leaf_hash or trusted_root != self.expected_root:
                return False
            if self.leaf_index >= self.leaf_count:
                return False
            depth = (self.leaf_count - 1).bit_length()
            if len(self.sibling_hashes) != depth or len(self.sibling_is_right) != depth:
                return False
            current = _hash_leaf(leaf_hash)
            idx = self.leaf_index
            for sibling, is_right in zip(self.sibling_hashes, self.sibling_is_right):
                if is_right != (idx % 2 == 0):
                    return False
                current = _hash_pair(current, sibling) if is_right else _hash_pair(sibling, current)
                idx //= 2
            return current == trusted_root
        except (ValueError, TypeError):
            return False


class FoldedCausalEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = FOLD_SCHEMA
    envelope_id: UUID
    fold_depth: int = Field(ge=1)
    record_count: int = Field(ge=1, le=MAX_FOLD_RECORDS)
    start_seq_no: int = Field(ge=1)
    end_seq_no: int = Field(ge=1)
    initial_chain_head: str = Field(pattern=r"^[a-f0-9]{64}$")
    final_chain_head: str = Field(pattern=r"^[a-f0-9]{64}$")
    merkle_root: str = Field(pattern=r"^[a-f0-9]{64}$")
    net_value_delta_micro_units: int
    total_energy_nanojoules: int = Field(ge=0)
    folded_at_utc: datetime
    aggregator_pub_hex: str = Field(pattern=r"^[a-f0-9]{64}$")
    aggregator_sig_hex: str = Field(pattern=r"^[a-f0-9]{128}$")

    @model_validator(mode="after")
    def check_bounds(self) -> "FoldedCausalEnvelope":
        if self.schema_version != FOLD_SCHEMA:
            raise ValueError("unsupported fold schema")
        if self.end_seq_no - self.start_seq_no + 1 != self.record_count:
            raise ValueError("aggregate sequence bounds disagree")
        if self.folded_at_utc.tzinfo is None:
            raise ValueError("fold time must be timezone aware")
        return self

    @property
    def total_joules_settled(self) -> float:
        return self.total_energy_nanojoules / 1_000_000_000

    def header_payload(self) -> bytes:
        return canonical_json({
            "schema_version": self.schema_version,
            "envelope_id": str(self.envelope_id),
            "fold_depth": self.fold_depth,
            "record_count": self.record_count,
            "start_seq_no": self.start_seq_no,
            "end_seq_no": self.end_seq_no,
            "initial_chain_head": self.initial_chain_head,
            "final_chain_head": self.final_chain_head,
            "merkle_root": self.merkle_root,
            "net_value_delta_micro_units": self.net_value_delta_micro_units,
            "total_energy_nanojoules": self.total_energy_nanojoules,
            "folded_at_utc": self.folded_at_utc.astimezone(timezone.utc).isoformat(),
            "aggregator_pub_hex": self.aggregator_pub_hex,
        })

    def envelope_hash(self) -> str:
        return sha256_hex(b"KINDRED-FOLDED-ENVELOPE-v1\x00" + self.header_payload() +
                          bytes.fromhex(self.aggregator_sig_hex))

    def verify_envelope(self, *, trusted_aggregator_pub_hex: str) -> bool:
        """Verify a claim signed by an explicitly trusted, pinned aggregator key."""
        if trusted_aggregator_pub_hex != self.aggregator_pub_hex:
            return False
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(trusted_aggregator_pub_hex)).verify(
                bytes.fromhex(self.aggregator_sig_hex), self.header_payload()
            )
            return True
        except (ValueError, Exception):
            return False


class CausalProofFolder:
    """Verifies records once, signs one claim, supports logarithmic inclusion proofs."""
    def __init__(self, aggregator_key: Ed25519PrivateKey) -> None:
        self._key = aggregator_key
        self.pub_hex = aggregator_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ).hex()

    @staticmethod
    def build_merkle_tree(leaf_hashes: Sequence[str]) -> list[list[str]]:
        return build_merkle_tree(leaf_hashes)

    @classmethod
    def generate_inclusion_proof(
        cls, leaf_hashes: Sequence[str], index: int
    ) -> MerkleInclusionProof:
        if index < 0 or index >= len(leaf_hashes):
            raise IndexError("leaf index out of bounds")
        levels = cls.build_merkle_tree(leaf_hashes)
        siblings: list[str] = []
        right_flags: list[bool] = []
        idx = index
        for level in levels[:-1]:
            padded = level if len(level) % 2 == 0 else level + [level[-1]]
            is_right = idx % 2 == 0
            siblings.append(padded[idx + 1] if is_right else padded[idx - 1])
            right_flags.append(is_right)
            idx //= 2
        return MerkleInclusionProof(
            leaf_index=index, leaf_count=len(leaf_hashes),
            leaf_hash=leaf_hashes[index],
            sibling_hashes=tuple(siblings),
            sibling_is_right=tuple(right_flags),
            expected_root=levels[-1][0],
        )

    def _sign(self, *, depth: int, record_count: int, start: int, end: int,
              initial: str, final: str, root: str, net: int, nanojoules: int) -> FoldedCausalEnvelope:
        unsigned = FoldedCausalEnvelope(
            envelope_id=uuid4(), fold_depth=depth, record_count=record_count,
            start_seq_no=start, end_seq_no=end, initial_chain_head=initial,
            final_chain_head=final, merkle_root=root,
            net_value_delta_micro_units=net, total_energy_nanojoules=nanojoules,
            folded_at_utc=datetime.now(timezone.utc), aggregator_pub_hex=self.pub_hex,
            aggregator_sig_hex="0" * 128,
        )
        return unsigned.model_copy(
            update={"aggregator_sig_hex": self._key.sign(unsigned.header_payload()).hex()}
        )

    def fold_records(
        self, records: Sequence[BilateralEntanglementRecord],
        verify_individual_sigs: bool = True,
    ) -> tuple[FoldedCausalEnvelope, list[str]]:
        if not records or len(records) > MAX_FOLD_RECORDS:
            raise ValueError("batch length out of bounds")
        hashes: list[str] = []
        expected_seq = records[0].seq_no
        head = records[0].initiator_prev_hash
        net_value = 0
        nanojoules = 0
        keys = (records[0].initiator_pub_hex, records[0].counterparty_pub_hex)
        for record in records:
            if (record.initiator_pub_hex, record.counterparty_pub_hex) != keys:
                raise ValueError("batch changes signing participants")
            if verify_individual_sigs and not record.verify_bilateral_signatures():
                raise PermissionError(f"invalid bilateral record signatures at sequence {expected_seq}")
            if record.seq_no != expected_seq or record.initiator_prev_hash != head or record.counterparty_prev_hash != head:
                raise ValueError(f"broken bilateral sequence/causal link at {expected_seq}")
            head = record.commitment_hash()
            hashes.append(head)
            expected_seq += 1
            net_value += record.value_delta_micro_units
            nanojoules += record.energy_nanojoules
        return self._sign(
            depth=1, record_count=len(records), start=records[0].seq_no,
            end=records[-1].seq_no, initial=records[0].initiator_prev_hash,
            final=head, root=self.build_merkle_tree(hashes)[-1][0],
            net=net_value, nanojoules=nanojoules,
        ), hashes

    def recursive_fold_envelopes(
        self, envelopes: Iterable[FoldedCausalEnvelope],
    ) -> FoldedCausalEnvelope:
        """Signs and aggregates previously signed summaries; not recursive ZK proof folding."""
        batch = list(envelopes)
        if not batch or len(batch) > MAX_FOLD_RECORDS:
            raise ValueError("invalid child envelope count")
        record_count = 0
        net = 0
        nanojoules = 0
        hashes = []
        depth = 0
        for i, env in enumerate(batch):
            if not env.verify_envelope(trusted_aggregator_pub_hex=self.pub_hex):
                raise PermissionError("child envelope signer is not trusted or signature is invalid")
            if i:
                prior = batch[i - 1]
                if env.start_seq_no != prior.end_seq_no + 1 or env.initial_chain_head != prior.final_chain_head:
                    raise ValueError("disjoint child envelope causal chain")
            record_count += env.record_count
            if record_count > MAX_FOLD_RECORDS:
                raise ValueError("aggregate exceeds maximum count")
            net += env.net_value_delta_micro_units
            nanojoules += env.total_energy_nanojoules
            depth = max(depth, env.fold_depth)
            hashes.append(env.envelope_hash())
        return self._sign(
            depth=depth + 1, record_count=record_count,
            start=batch[0].start_seq_no, end=batch[-1].end_seq_no,
            initial=batch[0].initial_chain_head, final=batch[-1].final_chain_head,
            root=self.build_merkle_tree(hashes)[-1][0], net=net,
            nanojoules=nanojoules,
        )

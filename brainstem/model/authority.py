"""Loopback-only Ed25519 founder approval records using Python cryptography."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from brainstem.runtime.paths import global_state_dir
from brainstem.runtime.store import StateStore, now


class FounderAuthority:
    def __init__(self, store: StateStore, key_dir: Path | None = None) -> None:
        self.store = store
        self.key_dir = key_dir or global_state_dir() / "authority"
        self.private_key = self.key_dir / "founder-ed25519-private.pem"
        self.public_key = self.key_dir / "founder-ed25519-public.pem"

    def _load_private_key(self) -> Ed25519PrivateKey:
        key = serialization.load_pem_private_key(
            self.private_key.read_bytes(), password=None
        )
        if not isinstance(key, Ed25519PrivateKey):
            raise TypeError("Founder private key is not Ed25519.")
        return key

    def _load_public_key(self) -> Ed25519PublicKey:
        key = serialization.load_pem_public_key(self.public_key.read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise TypeError("Founder public key is not Ed25519.")
        return key

    def initialize(self) -> str:
        self.key_dir.mkdir(parents=True, exist_ok=True)
        if not self.private_key.exists():
            private_key = Ed25519PrivateKey.generate()
            self.private_key.write_bytes(
                private_key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            os.chmod(self.private_key, 0o600)
        else:
            private_key = self._load_private_key()

        if not self.public_key.exists():
            self.public_key.write_bytes(
                private_key.public_key().public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )
            os.chmod(self.public_key, 0o644)
        else:
            self._load_public_key()

        return hashlib.sha256(self.public_key.read_bytes()).hexdigest()

    def _payload(
        self,
        action: str,
        scope: str,
        checkpoint_hash: str | None,
        expires_at: str | None,
    ) -> dict[str, Any]:
        return {
            "founder_public_key_id": self.initialize(),
            "action": action,
            "action_hash": hashlib.sha256(action.encode()).hexdigest(),
            "scope": scope,
            "checkpoint_hash": checkpoint_hash,
            "timestamp": now(),
            "expires_at": expires_at,
            "revoked": False,
        }

    def sign(
        self,
        action: str,
        scope: str,
        checkpoint_hash: str | None = None,
        expires_at: str | None = None,
        decision: str = "APPROVED",
    ) -> str:
        payload = self._payload(action, scope, checkpoint_hash, expires_at)
        message = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        signature = base64.b64encode(
            self._load_private_key().sign(message)
        ).decode()
        record_id = f"KSIGN-{hashlib.sha256((signature + payload['timestamp']).encode()).hexdigest()[:12].upper()}"
        record = {"payload": payload, "signature": signature, "decision": decision}
        timestamp = now()
        self.store.execute(
            "INSERT INTO signed_approvals VALUES(?,?,?,?,?,?)",
            (
                record_id,
                decision,
                json.dumps(record, sort_keys=True),
                hashlib.sha256(message).hexdigest(),
                timestamp,
                timestamp,
            ),
        )
        return record_id

    def verify(
        self,
        record_id: str,
        expected_action: str | None = None,
        expected_checkpoint_hash: str | None = None,
    ) -> bool:
        rows = self.store.query(
            "SELECT * FROM signed_approvals WHERE id=?", (record_id,)
        )
        if not rows:
            return False
        record = json.loads(rows[0]["payload"])
        payload = record["payload"]
        if (
            payload.get("revoked")
            or (expected_action and payload.get("action") != expected_action)
            or (
                expected_checkpoint_hash is not None
                and payload.get("checkpoint_hash") != expected_checkpoint_hash
            )
        ):
            return False
        if payload.get("expires_at") and datetime.fromisoformat(
            payload["expires_at"]
        ) < datetime.now(timezone.utc):
            return False
        message = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        try:
            signature = base64.b64decode(record["signature"], validate=True)
        except Exception:
            return False
        try:
            self._load_public_key().verify(signature, message)
        except (InvalidSignature, ValueError, TypeError, OSError):
            return False
        return True

    def revoke(self, record_id: str) -> None:
        row = self.store.query(
            "SELECT payload FROM signed_approvals WHERE id=?", (record_id,)
        )[0]
        record = json.loads(row["payload"])
        record["payload"]["revoked"] = True
        self.store.execute(
            "UPDATE signed_approvals SET status='REVOKED',payload=?,updated_at=? WHERE id=?",
            (json.dumps(record, sort_keys=True), now(), record_id),
        )

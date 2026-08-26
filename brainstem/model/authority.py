"""Cryptographically authenticated, context-bound founder decisions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from brainstem.runtime.paths import global_state_dir
from brainstem.runtime.store import StateStore, now

Decision = Literal["APPROVED", "REJECTED"]
DEFAULT_DECISION_TTL = timedelta(minutes=15)


class FounderAuthority:
    """Issue and verify Ed25519 decisions rooted in the configured local key."""

    def __init__(self, store: StateStore, key_dir: Path | None = None) -> None:
        self.store = store
        self.key_dir = key_dir or global_state_dir() / "authority"
        self.private_key = self.key_dir / "founder-ed25519-private.pem"
        self.public_key = self.key_dir / "founder-ed25519-public.pem"

    @staticmethod
    def _canonical(value: Any) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

    @staticmethod
    def _same(left: str, right: str) -> bool:
        return hmac.compare_digest(left.encode(), right.encode())

    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(UTC)

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

    def _public_der(self, key: Ed25519PublicKey | None = None) -> bytes:
        return (key or self._load_public_key()).public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def key_id(self) -> str:
        return f"ed25519-sha256:{hashlib.sha256(self._public_der()).hexdigest()}"

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

        derived_public = private_key.public_key()
        if not self.public_key.exists():
            self.public_key.write_bytes(
                derived_public.public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )
            os.chmod(self.public_key, 0o644)
        else:
            stored_public = self._load_public_key()
            if not hmac.compare_digest(
                self._public_der(derived_public), self._public_der(stored_public)
            ):
                raise ValueError("Founder private and public keys do not match.")

        return self.key_id()

    def sign(
        self,
        action: str,
        scope: str,
        payload_digest: str | None = None,
        expires_at: str | None = None,
        decision: Decision = "APPROVED",
        *,
        environment: str = "local",
        tenant: str = "default",
        nonce: str | None = None,
    ) -> str:
        """Sign a bounded decision. The public display name is never an input."""
        if decision not in {"APPROVED", "REJECTED"}:
            raise ValueError("Decision must be APPROVED or REJECTED.")
        if not all(
            isinstance(item, str) and item
            for item in (action, scope, environment, tenant)
        ):
            raise ValueError("Action, scope, environment, and tenant are required.")
        if payload_digest is not None and (
            len(payload_digest) != 64
            or any(character not in "0123456789abcdef" for character in payload_digest)
        ):
            raise ValueError("Payload digest must be a lowercase SHA-256 hex digest.")
        issued = datetime.now(UTC)
        expiry = (
            self._parse_time(expires_at)
            if expires_at is not None
            else issued + DEFAULT_DECISION_TTL
        )
        if expiry is None or expiry <= issued:
            raise ValueError(
                "Decision expiry must be timezone-aware and after issuance."
            )
        key_id = self.initialize()
        payload: dict[str, Any] = {
            "schema_version": 2,
            "decision": decision,
            "action": action,
            "action_digest": hashlib.sha256(action.encode()).hexdigest(),
            "scope": scope,
            "payload_digest": payload_digest,
            "environment": environment,
            "tenant": tenant,
            "approver_identity": key_id,
            "issued_at": issued.isoformat(),
            "expires_at": expiry.isoformat(),
            "nonce": nonce or secrets.token_urlsafe(24),
        }
        message = self._canonical(payload)
        signature = self._load_private_key().sign(message)
        signature_text = base64.b64encode(signature).decode()
        record_id = f"KSIGN-{hashlib.sha256(signature).hexdigest()[:16].upper()}"
        record = {"payload": payload, "signature": signature_text}
        timestamp = now()
        try:
            with self.store.connect() as db:
                db.execute(
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
                db.execute(
                    "INSERT INTO approval_nonces(nonce,approval_id,used_at,created_at) VALUES(?,?,NULL,?)",
                    (payload["nonce"], record_id, timestamp),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                "Decision nonce or record identity was already issued."
            ) from exc
        return record_id

    def _validated(
        self,
        row: dict[str, Any],
        *,
        expected_action: str,
        expected_payload_digest: str | None,
        expected_environment: str,
        expected_tenant: str,
        expected_scope: str | None,
        expected_decision: Decision,
        check_expiry: bool,
    ) -> dict[str, Any] | None:
        if not self._same(str(row.get("status", "")), expected_decision):
            return None
        try:
            record = json.loads(row["payload"])
            payload = record["payload"]
            signature = base64.b64decode(record["signature"], validate=True)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        required = {
            "schema_version",
            "decision",
            "action",
            "action_digest",
            "scope",
            "payload_digest",
            "environment",
            "tenant",
            "approver_identity",
            "issued_at",
            "expires_at",
            "nonce",
        }
        if not isinstance(payload, dict) or set(payload) != required:
            return None
        values = {
            "decision": expected_decision,
            "action": expected_action,
            "action_digest": hashlib.sha256(expected_action.encode()).hexdigest(),
            "environment": expected_environment,
            "tenant": expected_tenant,
            "approver_identity": self.key_id(),
        }
        if expected_payload_digest is not None:
            values["payload_digest"] = expected_payload_digest
        if expected_scope is not None:
            values["scope"] = expected_scope
        for name, expected in values.items():
            actual = payload.get(name)
            if not isinstance(actual, str) or not self._same(actual, expected):
                return None
        if payload.get("schema_version") != 2:
            return None
        if (
            expected_payload_digest is None
            and payload.get("payload_digest") is not None
        ):
            return None
        nonce = payload.get("nonce")
        if not isinstance(nonce, str) or len(nonce) < 16:
            return None
        issued = self._parse_time(payload.get("issued_at"))
        expiry = self._parse_time(payload.get("expires_at"))
        current = datetime.now(UTC)
        if issued is None or expiry is None or issued >= expiry or issued > current:
            return None
        if check_expiry and expiry <= current:
            return None
        message = self._canonical(payload)
        digest = hashlib.sha256(message).hexdigest()
        if not self._same(str(row.get("content_hash", "")), digest):
            return None
        try:
            self._load_public_key().verify(signature, message)
        except (InvalidSignature, ValueError, TypeError, OSError):
            return None
        return payload

    def verify(
        self,
        record_id: str,
        expected_action: str,
        expected_payload_digest: str | None = None,
        *,
        expected_environment: str = "local",
        expected_tenant: str = "default",
        expected_scope: str | None = None,
        expected_decision: Decision = "APPROVED",
        check_expiry: bool = True,
    ) -> bool:
        rows = self.store.query(
            "SELECT * FROM signed_approvals WHERE id=?", (record_id,)
        )
        if not rows:
            return False
        try:
            return (
                self._validated(
                    rows[0],
                    expected_action=expected_action,
                    expected_payload_digest=expected_payload_digest,
                    expected_environment=expected_environment,
                    expected_tenant=expected_tenant,
                    expected_scope=expected_scope,
                    expected_decision=expected_decision,
                    check_expiry=check_expiry,
                )
                is not None
            )
        except (OSError, ValueError, TypeError):
            return False

    def authorize(
        self,
        record_id: str,
        expected_action: str,
        expected_payload_digest: str | None = None,
        *,
        expected_environment: str = "local",
        expected_tenant: str = "default",
        expected_scope: str | None = None,
        expected_decision: Decision = "APPROVED",
    ) -> bool:
        """Verify and atomically consume a decision nonce exactly once."""
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            selected = db.execute(
                "SELECT * FROM signed_approvals WHERE id=?", (record_id,)
            ).fetchone()
            if selected is None:
                return False
            try:
                payload = self._validated(
                    dict(selected),
                    expected_action=expected_action,
                    expected_payload_digest=expected_payload_digest,
                    expected_environment=expected_environment,
                    expected_tenant=expected_tenant,
                    expected_scope=expected_scope,
                    expected_decision=expected_decision,
                    check_expiry=True,
                )
            except (OSError, ValueError, TypeError):
                return False
            if payload is None:
                return False
            updated = db.execute(
                "UPDATE approval_nonces SET used_at=? WHERE nonce=? AND approval_id=? AND used_at IS NULL",
                (now(), payload["nonce"], record_id),
            )
            return updated.rowcount == 1

    def revoke(self, record_id: str) -> None:
        self._set_status(record_id, "REVOKED")

    def supersede(self, record_id: str) -> None:
        self._set_status(record_id, "SUPERSEDED")

    def _set_status(self, record_id: str, status: str) -> None:
        with self.store.connect() as db:
            updated = db.execute(
                "UPDATE signed_approvals SET status=?,updated_at=? WHERE id=?",
                (status, now(), record_id),
            )
            if updated.rowcount != 1:
                raise KeyError(record_id)

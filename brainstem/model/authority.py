"""Loopback-only Ed25519 founder approval records backed by OpenSSL."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brainstem.runtime.paths import global_state_dir
from brainstem.runtime.store import StateStore, now


class FounderAuthority:
    def __init__(self, store: StateStore, key_dir: Path | None = None) -> None:
        self.store = store
        self.key_dir = key_dir or global_state_dir() / "authority"
        self.private_key = self.key_dir / "founder-ed25519-private.pem"
        self.public_key = self.key_dir / "founder-ed25519-public.pem"

    def initialize(self) -> str:
        self.key_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.key_dir, 0o700)
        if not self.private_key.exists():
            subprocess.run(
                [
                    "openssl",
                    "genpkey",
                    "-algorithm",
                    "ED25519",
                    "-out",
                    str(self.private_key),
                ],
                check=True,
                capture_output=True,
            )
            os.chmod(self.private_key, 0o600)
            subprocess.run(
                [
                    "openssl",
                    "pkey",
                    "-in",
                    str(self.private_key),
                    "-pubout",
                    "-out",
                    str(self.public_key),
                ],
                check=True,
                capture_output=True,
            )
            os.chmod(self.public_key, 0o644)
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
        # The decision is authorization material, not unsigned display metadata.
        payload["decision"] = decision
        message = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        with tempfile.TemporaryDirectory() as directory:
            msg = Path(directory) / "message"
            sig = Path(directory) / "signature"
            msg.write_bytes(message)
            subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-sign",
                    "-inkey",
                    str(self.private_key),
                    "-rawin",
                    "-in",
                    str(msg),
                    "-out",
                    str(sig),
                ],
                check=True,
                capture_output=True,
            )
            signature = base64.b64encode(sig.read_bytes()).decode()
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
            rows[0]["status"] != "APPROVED"
            or record.get("decision") != "APPROVED"
            or payload.get("decision") != "APPROVED"
            or payload.get("revoked")
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
        with tempfile.TemporaryDirectory() as directory:
            msg = Path(directory) / "message"
            sig = Path(directory) / "signature"
            msg.write_bytes(message)
            sig.write_bytes(signature)
            result = subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-inkey",
                    str(self.public_key),
                    "-rawin",
                    "-in",
                    str(msg),
                    "-sigfile",
                    str(sig),
                ],
                capture_output=True,
            )
        return result.returncode == 0

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

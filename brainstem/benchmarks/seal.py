"""Process-independent benchmark seal and disposable-workspace policy."""

from __future__ import annotations
import json
import os
from pathlib import Path
from brainstem.runtime.paths import global_state_dir
from .contracts import utc_now


class BenchmarkSeal:
    def __init__(self, state_dir: Path | None = None):
        self.state_dir = state_dir or global_state_dir()
        self.path = self.state_dir / "benchmark-seal.json"

    def status(self) -> dict:
        if not self.path.exists():
            return {"sealed": False, "status": "UNSEALED"}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def seal(self) -> dict:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "sealed": True,
            "status": "SEALED",
            "sealed_at": utc_now(),
            "pid": os.getpid(),
            "policy_version": "1",
        }
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, sort_keys=True)
        return payload

    def unseal(self) -> dict:
        previous = self.status()
        self.path.unlink(missing_ok=True)
        return {"sealed": False, "status": "UNSEALED", "previous": previous}

    def require(self) -> None:
        if not self.status().get("sealed"):
            raise PermissionError("external benchmark runs require sealed mode")


BLOCKED_WRITE_TABLES = (
    "memory",
    "experiences",
    "experiences_v2",
    "beliefs",
    "learning_proposals",
    "datasets",
    "concepts",
    "skills",
    "skill_records",
    "missions",
)


def reject_canonical_write(sql: str, seal: BenchmarkSeal | None = None) -> None:
    if not (seal or BenchmarkSeal()).status().get("sealed"):
        return
    normalized = " ".join(sql.lower().split())
    if any(
        (f"insert into {t}" in normalized or f"update {t}" in normalized)
        for t in BLOCKED_WRITE_TABLES
    ):
        raise PermissionError(
            "canonical cognitive writes are blocked while benchmark mode is sealed"
        )

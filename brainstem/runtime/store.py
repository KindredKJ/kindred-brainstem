"""SQLite persistence and append-only audit export for BRAINSTEM."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    """Canonical local state store; every state transition emits an audit event."""

    def __init__(self, path: Path, audit_path: Path | None = None) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_path = audit_path or self.path.with_name("events.jsonl")
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY, title TEXT NOT NULL, model TEXT,
              status TEXT NOT NULL, repository TEXT, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
              role TEXT NOT NULL, content TEXT NOT NULL, model TEXT,
              created_at TEXT NOT NULL, FOREIGN KEY(session_id) REFERENCES sessions(id)
            );
            CREATE TABLE IF NOT EXISTS events (
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence (
              id TEXT PRIMARY KEY, session_id TEXT, kind TEXT NOT NULL,
              content TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memory (
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, content TEXT NOT NULL,
              status TEXT NOT NULL, evidence_id TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS learning (
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, proposal TEXT NOT NULL,
              status TEXT NOT NULL, evidence_id TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approvals (
              id TEXT PRIMARY KEY, action TEXT NOT NULL, status TEXT NOT NULL,
              founder TEXT NOT NULL, created_at TEXT NOT NULL
            );
            """)

    def event(self, kind: str, payload: dict[str, Any]) -> str:
        event_id = f"KEVT-{uuid.uuid4().hex[:12].upper()}"
        record = {"id": event_id, "kind": kind, "payload": payload, "created_at": now()}
        with self.connect() as db:
            db.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?)",
                (
                    event_id,
                    kind,
                    json.dumps(payload, sort_keys=True),
                    record["created_at"],
                ),
            )
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
        return event_id

    def create_session(
        self, model: str | None, repository: str | None = None
    ) -> dict[str, Any]:
        session_id = f"KBS-{uuid.uuid4().hex[:12].upper()}"
        timestamp = now()
        with self.connect() as db:
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    "BRAINSTEM conversation",
                    model,
                    "AVAILABLE",
                    repository,
                    timestamp,
                    timestamp,
                ),
            )
        self.event(
            "session.created",
            {"session_id": session_id, "model": model, "repository": repository},
        )
        return self.session(session_id)

    def session(self, session_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return dict(row)

    def latest_session(self) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def set_model(self, session_id: str, model: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE sessions SET model=?, updated_at=? WHERE id=?",
                (model, now(), session_id),
            )
        self.event("session.model_changed", {"session_id": session_id, "model": model})

    def add_message(
        self, session_id: str, role: str, content: str, model: str | None = None
    ) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO messages(session_id,role,content,model,created_at) VALUES(?,?,?,?,?)",
                (session_id, role, content, model, now()),
            )
            db.execute(
                "UPDATE sessions SET updated_at=? WHERE id=?", (now(), session_id)
            )
        self.event(
            "message.recorded", {"session_id": session_id, "role": role, "model": model}
        )

    def history(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT role,content,model,created_at FROM messages WHERE session_id=? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_evidence(
        self,
        session_id: str,
        kind: str,
        content: dict[str, Any],
        status: str = "VERIFIED",
    ) -> str:
        evidence_id = f"KEVD-{uuid.uuid4().hex[:12].upper()}"
        with self.connect() as db:
            db.execute(
                "INSERT INTO evidence VALUES(?,?,?,?,?,?)",
                (
                    evidence_id,
                    session_id,
                    kind,
                    json.dumps(content, sort_keys=True),
                    status,
                    now(),
                ),
            )
        self.event(
            "evidence.recorded",
            {
                "evidence_id": evidence_id,
                "session_id": session_id,
                "kind": kind,
                "status": status,
            },
        )
        return evidence_id

    def propose_learning(
        self, kind: str, proposal: str, evidence_id: str | None
    ) -> str:
        learning_id = f"KLP-{uuid.uuid4().hex[:12].upper()}"
        with self.connect() as db:
            db.execute(
                "INSERT INTO learning VALUES(?,?,?,?,?,?)",
                (learning_id, kind, proposal, "PROPOSED", evidence_id, now()),
            )
        self.event(
            "learning.proposed", {"learning_id": learning_id, "status": "PROPOSED"}
        )
        return learning_id

    def backup(self, destination: Path) -> Path:
        """Create a transactionally consistent SQLite backup."""
        destination = destination.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source, sqlite3.connect(destination) as target:
            source.backup(target)
        self.event("state.backed_up", {"destination": str(destination)})
        return destination

    @classmethod
    def restore(
        cls, backup: Path, destination: Path, audit_path: Path | None = None
    ) -> "StateStore":
        """Restore a validated SQLite backup into a new canonical location."""
        backup = backup.expanduser().resolve()
        if not backup.is_file():
            raise FileNotFoundError(backup)
        destination = destination.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(backup) as source, sqlite3.connect(destination) as target:
            if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup failed SQLite integrity check")
            source.backup(target)
        restored = cls(destination, audit_path)
        restored.event("state.restored", {"source": str(backup)})
        return restored

    def counts(self) -> dict[str, int]:
        with self.connect() as db:
            names = (
                "sessions",
                "messages",
                "events",
                "evidence",
                "memory",
                "learning",
                "approvals",
            )
            return {
                name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in names
            }

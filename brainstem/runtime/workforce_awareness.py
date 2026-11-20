"""BRAINSTEM-owned operational awareness, with EMIT as an optional observation source.

No external worker is considered live merely because it was configured or registered.
This module persists worker observations in BRAINSTEM's canonical SQLite store.
"""

from __future__ import annotations

import json
import os
import re
import hmac
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from brainstem.runtime.store import StateStore

WORKFORCE_SCHEMA = "kindred.workforce.inventory.v1"
OBSERVATION_TTL_SECONDS = 60
MAX_CLOCK_SKEW_SECONDS = 5.0
MAX_OBSERVATION_AGE_SECONDS = 45.0
MAX_RESPONSE_BYTES = 2_000_000
IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_seconds(value: str, now: datetime) -> float:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return float("inf")
        delta = (now - parsed).total_seconds()
        return max(0.0, delta) if delta >= -MAX_CLOCK_SKEW_SECONDS else float("inf")
    except (ValueError, TypeError, AttributeError):
        return float("inf")


def _sanitize_error_message(exc: Exception | str, secret: str | None = None) -> str:
    """Remove configured credentials and byte-literal header values before persistence."""
    msg = f"{type(exc).__name__}: {exc}" if isinstance(exc, Exception) else str(exc)
    if secret:
        for candidate in (secret, secret.strip(), repr(secret)):
            if candidate:
                msg = msg.replace(candidate, "[REDACTED]")
    msg = re.sub(r"""b(['"]).*?\1""", "b'[REDACTED]'", msg)
    msg = re.sub(r"(?i)(x-kindred-internal-key|authorization)\s*[:=]\s*[^\s,;]+",
                 r"\1=[REDACTED]", msg)
    return msg[:300]


def _identifier(value: str, name: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid {name}")
    return value


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("worker inventory redirects are not allowed")


class OperationalAwareness:
    """Native, persistent organization observations that survive EMIT outages."""

    def __init__(self, store: StateStore):
        self.store = store
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workforce_observations (
                    source TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    reported_status TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY(source, worker_id)
                );
                CREATE TABLE IF NOT EXISTS workforce_sources (
                    source TEXT PRIMARY KEY,
                    last_success_at TEXT,
                    last_error TEXT,
                    summary TEXT NOT NULL DEFAULT '{}'
                );
            """)

    def observe(
        self,
        source: str,
        worker_id: str,
        kind: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source = _identifier(source, "source")
        worker_id = _identifier(worker_id, "worker_id")
        kind = _identifier(kind, "kind")
        if status not in {"online", "busy", "degraded", "offline", "not_confirmed_online"}:
            raise ValueError("invalid status")
        if source == "kindred_emit_core":
            raise ValueError("EMIT observations must use its authenticated inventory")
        if not isinstance(details, (dict, type(None))):
            raise ValueError("details must be an object")
        record = {
            "source": source,
            "worker_id": worker_id,
            "kind": kind,
            "reported_status": status,
            "observed_at": _timestamp(),
            "verification": "authenticated_source_report_not_independent_proof",
            "details": details or {},
        }
        self._upsert([record])
        self.store.event("awareness.worker_observed", {
            "source": source, "worker_id": worker_id, "reported_status": status
        })
        return record

    @staticmethod
    def _upsert_with_connection(db, records: list[dict[str, Any]]) -> None:
        for record in records:
            db.execute(
                    """INSERT INTO workforce_observations
                       (source, worker_id, kind, reported_status, observed_at, payload)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(source, worker_id) DO UPDATE SET
                       kind=excluded.kind, reported_status=excluded.reported_status,
                       observed_at=excluded.observed_at, payload=excluded.payload""",
                    (
                        record["source"], record["worker_id"], record["kind"],
                        record["reported_status"], record["observed_at"],
                        json.dumps(record, sort_keys=True),
                    ),
            )

    def _upsert(self, records: list[dict[str, Any]]) -> None:
        with self.store.connect() as db:
            self._upsert_with_connection(db, records)

    def ingest_emit(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(snapshot, dict) or snapshot.get("schema_version") != WORKFORCE_SCHEMA:
            raise ValueError("unsupported workforce inventory contract")
        if snapshot.get("source") != "kindred_emit_core":
            raise ValueError("untrusted workforce source")
        now = datetime.now(timezone.utc)
        age = _age_seconds(snapshot.get("observed_at"), now)
        if age > MAX_OBSERVATION_AGE_SECONDS:
            raise ValueError("stale or invalid inventory snapshot")
        workers = snapshot.get("workers")
        registrations = snapshot.get("registered_agents")
        if not isinstance(workers, list) or not isinstance(registrations, list) or len(workers) > 4096 or len(registrations) > 4096:
            raise ValueError("invalid inventory collections")
        records = []
        seen = set()
        for raw in workers:
            if not isinstance(raw, dict):
                raise ValueError("invalid worker record")
            wid = _identifier(raw.get("worker_id"), "worker_id")
            if wid in seen:
                raise ValueError("duplicate worker_id")
            seen.add(wid)
            if raw.get("kind") != "signal_lane":
                raise ValueError("unexpected EMIT worker kind")
            status = "online" if raw.get("status") == "online" else "not_confirmed_online"
            if _age_seconds(raw.get("last_seen"), now) > MAX_OBSERVATION_AGE_SECONDS:
                status = "not_confirmed_online"
            records.append({
                "source": "kindred_emit_core",
                "worker_id": wid,
                "kind": "signal_lane",
                "reported_status": status,
                "observed_at": now.isoformat(),
                "verification": "emit_heartbeat_observed_not_external_execution",
                "details": {
                    "lane": raw.get("lane"),
                    "processed_signals": raw.get("processed_signals", 0),
                    "failure_count": raw.get("failure_count", 0),
                    "last_seen": raw.get("last_seen"),
                    "capabilities": raw.get("capabilities", []) if isinstance(raw.get("capabilities"), list) else [],
                    "external_action_verified": False,
                },
            })
        summary = snapshot.get("summary")
        if not isinstance(summary, dict):
            raise ValueError("missing inventory summary")
        clean_summary = {
            "configured_lane_definitions": int(summary.get("configured_lane_definitions", 0)),
            "registered_agent_records": len(registrations),
            "observed_agent_processes": 0,
            "observed_lane_instances": len(records),
        }
        if not 0 <= clean_summary["configured_lane_definitions"] <= 4096:
            raise ValueError("invalid configured worker count")
        at = now.isoformat()
        with self.store.connect() as db:
            # One writer owns the entire invalidate + upsert + summary transition.
            # A failed ingestion rolls back without exposing an empty online set.
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """UPDATE workforce_observations SET reported_status='not_confirmed_online'
                   WHERE source='kindred_emit_core'"""
            )
            self._upsert_with_connection(db, records)
            db.execute(
                """INSERT INTO workforce_sources (source, last_success_at, last_error, summary)
                   VALUES (?, ?, NULL, ?)
                   ON CONFLICT(source) DO UPDATE SET
                   last_success_at=excluded.last_success_at,
                   last_error=NULL, summary=excluded.summary""",
                ("kindred_emit_core", at, json.dumps(clean_summary)),
            )
        self.store.event("awareness.emit_inventory_ingested", {
            "worker_instances": len(records),
            "registered_agent_records": len(registrations),
        })
        return self.overview()

    def _sync_failure(self, message: str) -> dict[str, Any]:
        safe = _sanitize_error_message(message, os.getenv("KINDRED_INTERNAL_SERVICE_KEY", ""))
        with self.store.connect() as db:
            db.execute(
                """INSERT INTO workforce_sources (source, last_success_at, last_error, summary)
                   VALUES ('kindred_emit_core', NULL, ?, '{}')
                   ON CONFLICT(source) DO UPDATE SET last_error=excluded.last_error""",
                (safe,),
            )
        self.store.event("awareness.emit_sync_failed", {"error": safe})
        return {"status": "unavailable", "source": "kindred_emit_core", "error": safe}

    def sync_emit(self) -> dict[str, Any]:
        base = os.getenv("KINDRED_EMIT_CORE_URL", "").rstrip("/")
        key = os.getenv("KINDRED_INTERNAL_SERVICE_KEY", "")
        if not base or not key:
            return {"status": "not_configured", "source": "kindred_emit_core"}
        url = urlsplit(base)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if (url.scheme != "https" and not (url.scheme == "http" and local)) or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}:
            return self._sync_failure("invalid EMIT address; require HTTPS or loopback HTTP")
        request = Request(
            base + "/runtime/workers/inventory",
            headers={"X-Kindred-Internal-Key": key, "Accept": "application/json"},
        )
        try:
            # Explicitly avoid machine-wide HTTP proxies only for the local EMIT bridge.
            # Preserve configured transport for remote HTTPS deployments.
            handlers = [_NoRedirect()]
            if local:
                handlers.insert(0, ProxyHandler({}))
            with build_opener(*handlers).open(request, timeout=10) as response:
                payload = response.read(MAX_RESPONSE_BYTES + 1)
                if len(payload) > MAX_RESPONSE_BYTES:
                    raise ValueError("inventory response exceeds limit")
            return self.ingest_emit(json.loads(payload))
        except Exception as exc:
            return self._sync_failure(_sanitize_error_message(exc, key))

    def overview(self) -> dict[str, Any]:
        current = datetime.now(timezone.utc)
        with self.store.connect() as db:
            records = [dict(r) for r in db.execute(
                "SELECT * FROM workforce_observations ORDER BY source, worker_id"
            )]
            sources = [dict(r) for r in db.execute(
                "SELECT * FROM workforce_sources ORDER BY source"
            )]
        workers = []
        for row in records:
            fresh = _age_seconds(row["observed_at"], current) <= OBSERVATION_TTL_SECONDS
            status = row["reported_status"] if fresh else "stale"
            workers.append({
                **json.loads(row["payload"]),
                "status": status,
                "fresh": fresh,
            })
        configured = 0
        registered = 0
        for source in sources:
            source["summary"] = json.loads(source["summary"])
            configured += source["summary"].get("configured_lane_definitions", 0)
            registered += source["summary"].get("registered_agent_records", 0)
        online = sum(w["status"] in {"online", "busy"} for w in workers)
        return {
            "status": "observations_available" if workers else "no_worker_observations",
            "observed_at": _timestamp(),
            "source_of_truth": "brainstem_local_state",
            "workers": workers,
            "sources": sources,
            "summary": {
                "observed_worker_records": len(workers),
                "online_workers": online,
                "not_confirmed_online": len(workers) - online,
                "configured_emit_lane_definitions": configured,
                "registered_emit_agent_records": registered,
                "independently_verified_external_workers": 0,
            },
        }

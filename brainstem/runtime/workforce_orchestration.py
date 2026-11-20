"""BRAINSTEM-owned durable workforce leases and verifiable EMIT execution.

Tasks are executable only under immutable typed contracts and recently authenticated
signal-lane observations. A signed EMIT receipt attests to *local queue execution*,
not independent verification of an external agent.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from brainstem.runtime.operators import AgenticContractRegistry, ContractViolationError, iso, utcnow, WorkforceOperatorSupervisor
from brainstem.runtime.causal_verification import verify_process_attestation
from brainstem.fabric.autopoietic import AutopoieticFabric
from brainstem.runtime.store import StateStore
from brainstem.runtime.workforce_awareness import OperationalAwareness, _NoRedirect, _age_seconds, _sanitize_error_message

RECEIPT_SCHEMA = "kindred.workforce.execution.receipt.v1"
MAX_PAYLOAD_BYTES = 16384
MAX_RECEIPT_BYTES = 65536
MAX_ACTIVE_LEASE_RENEWALS = 2


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


class OrchestrationError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class WorkforceOrchestrator:
    def __init__(self, store: StateStore, awareness: OperationalAwareness):
        self.store = store
        self.awareness = awareness
        self.contracts = AgenticContractRegistry(store)
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workforce_tasks (
                    task_id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    assigned_source TEXT,
                    assigned_worker_id TEXT,
                    contract_id TEXT NOT NULL,
                    required_capability TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(
                        status IN ('blocked','queued','leased','dispatched','verified_complete',
                                   'failed','expired','dead_letter')
                    ),
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL,
                    next_eligible_at TEXT,
                    lease_expires_at TEXT NOT NULL,
                    lease_seconds INTEGER NOT NULL,
                    lease_renewals INTEGER NOT NULL DEFAULT 0,
                    depends_on_json TEXT NOT NULL DEFAULT '[]',
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(assigned_source,assigned_worker_id)
                        REFERENCES workforce_observations(source,worker_id),
                    FOREIGN KEY(contract_id) REFERENCES agentic_contracts(contract_id)
                );
                CREATE INDEX IF NOT EXISTS idx_workforce_tasks_status_lease
                    ON workforce_tasks(status,lease_expires_at);
                CREATE INDEX IF NOT EXISTS idx_workforce_tasks_worker
                    ON workforce_tasks(assigned_source,assigned_worker_id,status);
                CREATE TABLE IF NOT EXISTS task_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    task_id TEXT UNIQUE NOT NULL,
                    worker_id TEXT NOT NULL,
                    output_sha256 TEXT NOT NULL,
                    output_json TEXT NOT NULL,
                    worker_signature TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    verified_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES workforce_tasks(task_id)
                );
                CREATE TABLE IF NOT EXISTS operator_audit_log (
                    event_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    operator_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES workforce_tasks(task_id)
                );
                CREATE TABLE IF NOT EXISTS workforce_circuits (
                    source TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    failures INTEGER NOT NULL DEFAULT 0,
                    open_until TEXT,
                    PRIMARY KEY(source,worker_id)
                );
            """)
        # KACF shares the same StateStore: no second worker queue or world authority.
        self.fabric = AutopoieticFabric(store)

    @staticmethod
    def _record(db, task_id: str) -> dict[str, Any] | None:
        row = db.execute("SELECT * FROM workforce_tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        result["depends_on"] = json.loads(result.pop("depends_on_json"))
        receipt = db.execute("SELECT * FROM task_receipts WHERE task_id=?", (task_id,)).fetchone()
        result["verified_receipt"] = json.loads(receipt["receipt_json"]) if receipt else None
        return result

    def task(self, task_id: str) -> dict[str, Any]:
        with self.store.connect() as db:
            result = self._record(db, task_id)
        if result is None:
            raise OrchestrationError(404, "task not found")
        return result

    def summary(self, limit: int = 10) -> dict[str, Any]:
        limit = max(1, min(int(limit), 100))
        with self.store.connect() as db:
            tasks = [dict(row) for row in db.execute(
                """SELECT task_id,assigned_worker_id,required_capability,status,lease_expires_at
                   FROM workforce_tasks WHERE status IN ('leased','dispatched')
                   AND lease_expires_at>? ORDER BY created_at DESC""", (iso(),)
            )]
            receipts = [dict(row) for row in db.execute(
                """SELECT r.task_id,r.worker_id,t.contract_id,t.required_capability,
                          r.output_sha256,r.verified_at,r.receipt_json
                   FROM task_receipts r JOIN workforce_tasks t ON r.task_id=t.task_id
                   ORDER BY r.verified_at DESC LIMIT ?""", (limit,)
            )]
            for item in receipts:
                envelope = json.loads(item.pop("receipt_json"))
                proof = envelope.get("causal_proof")
                item["causal_chain_hash"] = proof.get("chain_hash") if isinstance(proof, dict) else None
                item["causal_sequence"] = proof.get("sequence") if isinstance(proof, dict) else None
        return {
            "active_leases": tasks,
            "verified_outcomes": receipts,
            "verification_scope": "authenticated_emit_local_lane_execution_not_external_agent_proof",
            "kacf": self.fabric.summary(limit),
        }

    @staticmethod
    def _base():
        base = os.getenv("KINDRED_EMIT_CORE_URL", "").rstrip("/")
        url = urlsplit(base)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if (not url.hostname or url.username or url.password or url.query or url.fragment
            or url.path not in {"", "/"} or
            (url.scheme != "https" and not (url.scheme == "http" and local))):
            raise OrchestrationError(503, "EMIT transport requires HTTPS or local loopback HTTP")
        return base, local

    def _request_emit(self, path: str, payload: dict[str, Any] | None = None,
                      *, allow_missing: bool = False) -> dict[str, Any] | None:
        key = os.getenv("KINDRED_INTERNAL_SERVICE_KEY", "")
        if not key:
            raise OrchestrationError(503, "EMIT service authentication is not configured")
        base, local = self._base()
        handlers = [_NoRedirect()]
        if local:
            handlers.insert(0, ProxyHandler({}))
        data = canonical(payload) if payload is not None else None
        request = Request(
            base + path, data=data,
            headers={"X-Kindred-Internal-Key": key, "Accept": "application/json",
                     "Content-Type": "application/json"},
            method="POST" if data is not None else "GET",
        )
        try:
            with build_opener(*handlers).open(request, timeout=20) as response:
                raw = response.read(MAX_RECEIPT_BYTES + 1)
                if len(raw) > MAX_RECEIPT_BYTES:
                    raise ValueError("EMIT response exceeds receipt byte limit")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("EMIT response must be a JSON object")
            return result
        except HTTPError as exc:
            if allow_missing and exc.code == 404:
                return None
            raise OrchestrationError(502, f"EMIT task transport HTTP {exc.code}") from None
        except Exception as exc:
            raise OrchestrationError(
                502, "EMIT transport: " + _sanitize_error_message(exc, key)
            ) from None

    def _verify(self, task: dict[str, Any], receipt: dict[str, Any]) -> None:
        key = os.getenv("KINDRED_INTERNAL_SERVICE_KEY", "")
        signature = receipt.get("signature")
        if not key or not isinstance(signature, str) or len(signature) != 64:
            raise OrchestrationError(502, "EMIT receipt lacks a verifiable signature")
        unsigned = {k: value for k, value in receipt.items() if k != "signature"}
        expected = hmac.new(key.encode("utf-8"), canonical(unsigned), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise OrchestrationError(502, "EMIT receipt signature mismatch")
        expected_fields = {
            "schema_version": RECEIPT_SCHEMA,
            "task_id": task["task_id"],
            "worker_id": task["assigned_worker_id"],
            "action": task["required_capability"],
            "payload_sha256": task["payload_sha256"],
            "verification": "emit_local_lane_worker_execution",
            "external_agent_execution_verified": False,
        }
        if any(receipt.get(k) != value for k, value in expected_fields.items()):
            raise OrchestrationError(502, "EMIT receipt does not match leased task")
        if receipt.get("status") not in ("completed", "failed") or not isinstance(receipt.get("output"), dict):
            raise OrchestrationError(502, "EMIT receipt status or output is invalid")
        # @v2 task contracts require a full attested local process trace.
        # @v1 receipts remain historically valid but cannot smuggle malformed proofs.
        contract = self.contracts.contract(task["contract_id"], require_active=False)
        if (contract["verification_tier"] == "signal_lane_causal"
            or "causal_proof" in receipt):
            if not verify_process_attestation(receipt):
                raise OrchestrationError(502, "PoECL causal receipt verification failed")
        age = _age_seconds(receipt.get("completed_at"), utcnow())
        if age == float("inf") or age > 180:
            raise OrchestrationError(502, "EMIT receipt timestamp is stale or invalid")
        if receipt["status"] == "completed":
            try:
                self.contracts.validate_output(task["contract_id"], receipt["output"])
            except ContractViolationError as exc:
                raise OrchestrationError(502, str(exc)) from exc

    def _record_failure(self, task_id: str, error: str) -> None:
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT assigned_source,assigned_worker_id,status FROM workforce_tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if row is None or row["status"] not in ("leased", "dispatched"):
                return
            db.execute(
                "UPDATE workforce_tasks SET status='failed',last_error=?,updated_at=? WHERE task_id=?",
                (error[:300], iso(), task_id),
            )
            if row["assigned_worker_id"]:
                db.execute(
                    """INSERT INTO workforce_circuits(source,worker_id,failures,open_until)
                       VALUES (?,?,1,NULL)
                       ON CONFLICT(source,worker_id) DO UPDATE SET failures=failures+1""",
                    (row["assigned_source"], row["assigned_worker_id"]),
                )
                circuit = db.execute(
                    "SELECT failures FROM workforce_circuits WHERE source=? AND worker_id=?",
                    (row["assigned_source"], row["assigned_worker_id"]),
                ).fetchone()
                if circuit["failures"] >= 3:
                    db.execute(
                        """UPDATE workforce_circuits SET open_until=?
                           WHERE source=? AND worker_id=?""",
                        (iso(utcnow() + timedelta(seconds=60)),
                         row["assigned_source"], row["assigned_worker_id"]),
                    )
                    WorkforceOperatorSupervisor.log(
                        db, task_id, "circuit_breaker", "opened",
                        "three consecutive execution failures; 60-second cooldown",
                    )
        self.store.event("orchestration.task_failed", {"task_id": task_id})

    def _commit_receipt(self, task_id: str, receipt: dict[str, Any]) -> dict[str, Any]:
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            record = self._record(db, task_id)
            if record is None:
                raise OrchestrationError(404, "task not found")
            if record["status"] == "verified_complete":
                return record
            if record["status"] not in ("leased", "dispatched"):
                raise OrchestrationError(409, "task lease is not active")
            if record["lease_expires_at"] <= iso():
                raise OrchestrationError(409, "task lease expired before receipt verification")
            self._verify(record, receipt)
            # Rolling-upgrade compatibility: preexisting queued tasks lack KACF forks.
            # Prepare a non-executable fork only after the receipt is authenticated.
            self.fabric.prepare_in_transaction(
                db, task_id=task_id, capability=record["required_capability"],
                payload_sha256=record["payload_sha256"],
            )
            if receipt["status"] == "failed":
                raise OrchestrationError(502, "EMIT worker returned a signed failure")
            db.execute(
                """INSERT INTO task_receipts
                   (receipt_id,task_id,worker_id,output_sha256,output_json,
                    worker_signature,receipt_json,verified_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    "rcpt_" + uuid.uuid4().hex, task_id, record["assigned_worker_id"],
                    digest(receipt["output"]), canonical(receipt["output"]).decode("utf-8"),
                    receipt["signature"], canonical(receipt).decode("utf-8"), iso(),
                ),
            )
            db.execute(
                "UPDATE workforce_tasks SET status='verified_complete',last_error=NULL,updated_at=? WHERE task_id=?",
                (iso(), task_id),
            )
            # Collapse happens inside the *same transaction* as the receipt insert.
            self.fabric.collapse_verified_in_transaction(db, task_id=task_id)
            db.execute(
                """UPDATE workforce_circuits SET failures=0,open_until=NULL
                   WHERE source=? AND worker_id=?""",
                (record["assigned_source"], record["assigned_worker_id"]),
            )
            WorkforceOperatorSupervisor.log(
                db, task_id, "receipt_verifier", "verified",
                "HMAC, task binding, output JSON schema and freshness passed",
            )
        self.store.event("orchestration.task_verified", {"task_id": task_id})
        return self.task(task_id)

    def _select_and_lease(self, task_id: str) -> dict[str, Any] | None:
        now = utcnow()
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM workforce_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if row is None or row["status"] != "queued":
                return None
            if row["next_eligible_at"] and row["next_eligible_at"] > iso(now):
                return None
            cutoff = iso(now - timedelta(seconds=45))
            candidates = db.execute(
                """SELECT o.source,o.worker_id,o.kind,o.reported_status,o.observed_at,
                          o.payload,c.open_until
                   FROM workforce_observations o
                   LEFT JOIN workforce_circuits c
                     ON c.source=o.source AND c.worker_id=o.worker_id
                   WHERE o.source='kindred_emit_core' AND o.kind='signal_lane'
                     AND o.reported_status='online' AND o.observed_at>=?
                     AND (c.open_until IS NULL OR c.open_until<=?)
                     AND NOT EXISTS (
                       SELECT 1 FROM workforce_tasks t
                       WHERE t.assigned_source=o.source AND t.assigned_worker_id=o.worker_id
                       AND t.status IN ('leased','dispatched')
                     )
                   ORDER BY o.worker_id""", (cutoff, iso(now))
            ).fetchall()
            selected = None
            for candidate in candidates:
                if row["assigned_worker_id"] and candidate["worker_id"] != row["assigned_worker_id"]:
                    continue
                observed = json.loads(candidate["payload"])
                if observed.get("verification") != "emit_heartbeat_observed_not_external_execution":
                    continue
                if row["required_capability"] in observed.get("details", {}).get("capabilities", []):
                    selected = candidate
                    break
            if selected is None:
                return None
            db.execute(
                """UPDATE workforce_tasks SET assigned_source=?,assigned_worker_id=?,
                   status='leased',attempt_count=attempt_count+1,lease_expires_at=?,
                   lease_renewals=0,updated_at=? WHERE task_id=?""",
                ("kindred_emit_core", selected["worker_id"],
                 iso(now + timedelta(seconds=row["lease_seconds"])), iso(now), task_id),
            )
            WorkforceOperatorSupervisor.log(
                db, task_id, "capability_router", "leased",
                "assigned fresh authenticated signal lane with declared execution capability",
            )
        return self.task(task_id)

    def _execute_leased(self, task_id: str) -> dict[str, Any]:
        record = self.task(task_id)
        try:
            existing = self._request_emit(
                "/runtime/workers/tasks/" + task_id, allow_missing=True,
            )
            if existing is not None and existing.get("receipt") is not None:
                receipt = existing["receipt"]
            else:
                response = self._request_emit("/runtime/workers/execute", {
                    "task_id": task_id,
                    "worker_id": record["assigned_worker_id"],
                    "action": record["required_capability"],
                    "payload": record["payload"],
                })
                receipt = response
            return self._commit_receipt(task_id, receipt)
        except OrchestrationError as exc:
            self._record_failure(task_id, exc.detail)
            raise

    def dispatch(self, *, idempotency_key: str, contract_id: str,
                 payload: dict[str, Any], lease_seconds: int = 60,
                 depends_on: list[str] | None = None) -> dict[str, Any]:
        if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 128:
            raise OrchestrationError(422, "invalid idempotency key")
        if not isinstance(payload, dict) or len(canonical(payload)) > MAX_PAYLOAD_BYTES:
            raise OrchestrationError(422, "payload must be a bounded JSON object")
        try:
            contract = self.contracts.validate_input(contract_id, payload)
        except ContractViolationError as exc:
            raise OrchestrationError(422, str(exc)) from exc
        if not 5 <= lease_seconds <= contract["max_lease_seconds"]:
            raise OrchestrationError(422, "lease duration exceeds contract bounds")
        dependencies = list(depends_on or [])
        if len(dependencies) > 16 or len(set(dependencies)) != len(dependencies):
            raise OrchestrationError(422, "invalid dependency list")
        now = iso()
        task_id = "tsk_" + uuid.uuid4().hex
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT task_id FROM workforce_tasks WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if existing:
                original = self._record(db, existing["task_id"])
                if (original["contract_id"] != contract_id or
                    original["payload_sha256"] != digest(payload) or
                    original["depends_on"] != dependencies):
                    raise OrchestrationError(409, "idempotency key used for different work")
                return original
            states = []
            for dep in dependencies:
                row = db.execute(
                    "SELECT status FROM workforce_tasks WHERE task_id=?", (dep,)
                ).fetchone()
                if row is None:
                    raise OrchestrationError(422, "dependency must be an existing task")
                states.append(row["status"])
            if any(state in ("failed", "dead_letter", "expired") for state in states):
                raise OrchestrationError(409, "dependency has failed")
            status = "queued" if all(s == "verified_complete" for s in states) else "blocked"
            db.execute(
                """INSERT INTO workforce_tasks
                   (task_id,idempotency_key,assigned_source,assigned_worker_id,
                    contract_id,required_capability,payload_json,payload_sha256,status,
                    attempt_count,max_retries,next_eligible_at,lease_expires_at,lease_seconds,
                    lease_renewals,depends_on_json,last_error,created_at,updated_at)
                   VALUES (?,?,NULL,NULL,?,?,?,?,?,0,?,?,?,?,0,?,NULL,?,?)""",
                (task_id,idempotency_key,contract_id,contract["capability"],
                 canonical(payload).decode("utf-8"),digest(payload),status,
                 contract["max_retries"],now,now,lease_seconds,
                 json.dumps(dependencies),now,now),
            )
            self.fabric.prepare_in_transaction(
                db, task_id=task_id, capability=contract["capability"],
                payload_sha256=digest(payload),
            )
            WorkforceOperatorSupervisor.log(db,task_id,"contract_dispatch","accepted",
                f"immutable contract {contract_id}; prerequisites={len(dependencies)}")
        if status == "blocked":
            return self.task(task_id)
        leased = self._select_and_lease(task_id)
        if leased is None:
            return self.task(task_id)
        return self._execute_leased(task_id)

    def retry_due(self) -> dict[str, int]:
        # The operator calls this on its deterministic tick; no new goals or payloads.
        with self.store.connect() as db:
            ids = [row["task_id"] for row in db.execute(
                """SELECT task_id FROM workforce_tasks
                   WHERE status='queued' AND (next_eligible_at IS NULL OR next_eligible_at<=?)
                   ORDER BY created_at LIMIT 25""", (iso(),)
            )]
        attempts = 0
        for task_id in ids:
            leased = self._select_and_lease(task_id)
            if leased is None:
                continue
            attempts += 1
            try:
                self._execute_leased(task_id)
            except OrchestrationError:
                # Failure is durably recorded and backoff decided by the operator.
                continue
        recovered = self.fabric.reconcile_terminal_incidents()
        return {"attempted": attempts, "hcm_recovery_proposals": recovered}

    def renew_lease(self, task_id: str, seconds: int = 15) -> dict[str, Any]:
        if not 5 <= seconds <= 60:
            raise OrchestrationError(422, "renewal must be between 5 and 60 seconds")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM workforce_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if row is None:
                raise OrchestrationError(404, "task not found")
            if row["status"] not in ("leased", "dispatched") or row["lease_expires_at"] <= iso():
                raise OrchestrationError(409, "task lease is not renewable")
            if row["lease_renewals"] >= MAX_ACTIVE_LEASE_RENEWALS:
                raise OrchestrationError(409, "lease renewal budget exhausted")
            worker = db.execute(
                """SELECT observed_at,reported_status FROM workforce_observations
                   WHERE source=? AND worker_id=?""",
                (row["assigned_source"],row["assigned_worker_id"]),
            ).fetchone()
            if worker is None or worker["reported_status"] != "online" or _age_seconds(worker["observed_at"], utcnow()) > 45:
                raise OrchestrationError(409, "assigned worker is no longer observed online")
            contract = self.contracts.contract(row["contract_id"])
            total = (datetime.fromisoformat(row["lease_expires_at"]) - datetime.fromisoformat(row["created_at"])).total_seconds() + seconds
            if total > contract["max_lease_seconds"] + 120:
                raise OrchestrationError(409, "lease renewal exceeds contract total budget")
            db.execute(
                """UPDATE workforce_tasks SET lease_expires_at=?,lease_renewals=lease_renewals+1,
                   updated_at=? WHERE task_id=?""",
                (iso(datetime.fromisoformat(row["lease_expires_at"]) + timedelta(seconds=seconds)),iso(),task_id),
            )
            WorkforceOperatorSupervisor.log(db,task_id,"lease_renewal","extended",
                f"observed worker online; extended {seconds}s")
        return self.task(task_id)

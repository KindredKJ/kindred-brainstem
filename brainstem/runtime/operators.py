"""Immutable JSON-Schema execution contracts and deterministic workforce operators.

No registry declaration is converted to an observed, executable worker.
Operators transition durable tasks; they never generate new goals or payloads.
"""
from __future__ import annotations

import asyncio
import json
import re
from functools import lru_cache
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from brainstem.runtime.store import StateStore


class ContractViolationError(ValueError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None = None) -> str:
    return (value or utcnow()).isoformat()


CONTRACT_NAME = re.compile(r"^[a-z][a-z0-9_.-]{1,63}@v[1-9][0-9]*$")
SCHEMA_VERSION = "https://json-schema.org/draft/2020-12/schema"
HEX64 = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
UTC_DATE_TIME = {"type": "string", "format": "date-time"}
BUILTIN_CONTRACTS = {
    "runtime.snapshot@v1": {
        "capability": "runtime.snapshot", "version": "v1",
        "input_schema": {"$schema": SCHEMA_VERSION, "type": "object",
                         "properties": {}, "additionalProperties": False},
        "output_schema": {"$schema": SCHEMA_VERSION, "type": "object",
                          "required": ["foundation_ready", "lane_definitions", "online_lane_workers", "captured_at"],
                          "properties": {
                              "foundation_ready": {"type": "boolean"},
                              "lane_definitions": {"type": "integer", "minimum": 0},
                              "online_lane_workers": {"type": "integer", "minimum": 0},
                              "captured_at": UTC_DATE_TIME,
                          }, "additionalProperties": False},
        "max_lease_seconds": 60, "max_retries": 2,
        "require_live_signal_lane": True, "verification_tier": "signal_lane",
    },
    "signal.deliver@v1": {
        "capability": "signal.deliver", "version": "v1",
        "input_schema": {"$schema": SCHEMA_VERSION, "type": "object",
                         "required": ["signal"],
                         "properties": {"signal": {"type": "string", "minLength": 1, "maxLength": 4096}},
                         "additionalProperties": False},
        "output_schema": {"$schema": SCHEMA_VERSION, "type": "object",
                          "required": ["lane", "signal_sha256", "processed_count_after"],
                          "properties": {
                              "lane": {"type": "string", "minLength": 1},
                              "signal_sha256": HEX64,
                              "processed_count_after": {"type": "integer", "minimum": 1},
                          }, "additionalProperties": False},
        "max_lease_seconds": 60, "max_retries": 2,
        "require_live_signal_lane": True, "verification_tier": "signal_lane",
    },
}


class AgenticContractRegistry:
    def __init__(self, store: StateStore):
        self.store = store
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS agentic_contracts (
                    contract_id TEXT PRIMARY KEY,
                    capability TEXT NOT NULL,
                    version TEXT NOT NULL,
                    input_schema_json TEXT NOT NULL,
                    output_schema_json TEXT NOT NULL,
                    max_lease_seconds INTEGER NOT NULL,
                    max_retries INTEGER NOT NULL,
                    require_live_signal_lane INTEGER NOT NULL,
                    verification_tier TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    UNIQUE(capability,version)
                );
            """)
        for contract_id, spec in BUILTIN_CONTRACTS.items():
            with store.connect() as db:
                existing = db.execute(
                    "SELECT contract_id FROM agentic_contracts WHERE contract_id=?",
                    (contract_id,),
                ).fetchone()
            if existing is None:
                self.register_contract(contract_id=contract_id, **spec)

    def register_contract(self, *, contract_id: str, capability: str, version: str,
                          input_schema: dict[str, Any], output_schema: dict[str, Any],
                          max_lease_seconds: int, max_retries: int,
                          require_live_signal_lane: bool = True,
                          verification_tier: str = "signal_lane") -> dict[str, Any]:
        if not CONTRACT_NAME.fullmatch(contract_id) or contract_id != f"{capability}@{version}":
            raise ContractViolationError("contract identity must be capability@vN")
        if verification_tier != "signal_lane" or not require_live_signal_lane:
            raise ContractViolationError("unverified agent execution tier is not enabled")
        if not 5 <= max_lease_seconds <= 3600 or not 0 <= max_retries <= 8:
            raise ContractViolationError("invalid execution resource bounds")
        try:
            Draft202012Validator.check_schema(input_schema)
            Draft202012Validator.check_schema(output_schema)
        except Exception as exc:
            raise ContractViolationError(f"invalid contract schema: {type(exc).__name__}") from exc
        record = {
            "contract_id": contract_id, "capability": capability, "version": version,
            "input_schema_json": json.dumps(input_schema, sort_keys=True),
            "output_schema_json": json.dumps(output_schema, sort_keys=True),
            "max_lease_seconds": max_lease_seconds, "max_retries": max_retries,
            "require_live_signal_lane": 1, "verification_tier": verification_tier,
            "active": 1,
        }
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM agentic_contracts WHERE contract_id=?", (contract_id,)).fetchone()
            if existing:
                # Same ID is immutable: repeat registration is idempotent only for identical bytes.
                if any(existing[k] != v for k, v in record.items()):
                    raise ContractViolationError("contract version already exists and is immutable")
            else:
                db.execute(
                    """INSERT INTO agentic_contracts
                       (contract_id,capability,version,input_schema_json,output_schema_json,
                        max_lease_seconds,max_retries,require_live_signal_lane,verification_tier,active,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    tuple(record.values()) + (iso(),),
                )
        return self.contract(contract_id)

    def contract(self, contract_id: str, *, require_active: bool = True) -> dict[str, Any]:
        with self.store.connect() as db:
            row = db.execute(
                "SELECT * FROM agentic_contracts WHERE contract_id=?", (contract_id,)
            ).fetchone()
        if row is None or (require_active and not row["active"]):
            raise ContractViolationError(f"active contract not found: {contract_id}")
        return dict(row)

    def deactivate_contract(self, contract_id: str) -> dict[str, Any]:
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM agentic_contracts WHERE contract_id=?", (contract_id,)
            ).fetchone()
            if row is None:
                raise ContractViolationError(f"contract not found: {contract_id}")
            db.execute("UPDATE agentic_contracts SET active=0 WHERE contract_id=?", (contract_id,))
        return self.contract(contract_id, require_active=False)

    def list_contracts(self) -> list[dict[str, Any]]:
        with self.store.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM agentic_contracts ORDER BY contract_id"
            )]

    @staticmethod
    @lru_cache(maxsize=256)
    def _validator(contract_id: str, schema_json: str) -> Draft202012Validator:
        return Draft202012Validator(
            json.loads(schema_json), format_checker=Draft202012Validator.FORMAT_CHECKER
        )

    def validate_input(self, contract_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        contract = self.contract(contract_id)
        try:
            self._validator(contract_id, contract["input_schema_json"]).validate(payload)
        except ValidationError as exc:
            raise ContractViolationError(f"input violates {contract_id}: {exc.message}") from exc
        return contract

    def validate_output(self, contract_id: str, output: dict[str, Any]) -> None:
        # Historical, immutable contract remains verifiable after deprecation.
        contract = self.contract(contract_id, require_active=False)
        try:
            self._validator(contract_id, contract["output_schema_json"]).validate(output)
        except ValidationError as exc:
            raise ContractViolationError(f"output violates {contract_id}: {exc.message}") from exc


class WorkforceOperatorSupervisor:
    """Durable lease, retry, circuit and dependency transitions without invented actions."""

    def __init__(self, store: StateStore, orchestrator: Any = None, tick_seconds: float = 5.0):
        self.store = store
        self.orchestrator = orchestrator
        self.tick_seconds = tick_seconds
        self._stop_event: asyncio.Event | None = None

    @staticmethod
    def log(db, task_id: str, operator: str, action: str, reason: str) -> None:
        db.execute(
            """INSERT INTO operator_audit_log
               (event_id,task_id,operator_name,action,reason,created_at)
               VALUES (?,?,?,?,?,?)""",
            ("opevt_" + uuid.uuid4().hex, task_id, operator, action, reason[:300], iso()),
        )

    def reconcile_once(self) -> dict[str, int]:
        now = utcnow()
        now_iso = iso(now)
        requeued = 0
        quarantined = 0
        released = 0
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for row in db.execute(
                """SELECT * FROM workforce_tasks WHERE
                   (status IN ('leased','dispatched') AND lease_expires_at<=?)
                   OR status='failed' ORDER BY created_at,task_id""", (now_iso,)
            ).fetchall():
                attempts = int(row["attempt_count"])
                retries = int(row["max_retries"])
                if attempts <= retries:
                    wait = min(60, 2 ** attempts)
                    db.execute(
                        """UPDATE workforce_tasks SET status='queued',next_eligible_at=?,
                           updated_at=? WHERE task_id=?""",
                        (iso(now + timedelta(seconds=wait)), now_iso, row["task_id"]),
                    )
                    self.log(db, row["task_id"], "retry_supervisor", "requeued",
                             f"attempt {attempts} of {retries + 1}; backoff {wait}s")
                    requeued += 1
                else:
                    db.execute(
                        """UPDATE workforce_tasks SET status='dead_letter',updated_at=?
                           WHERE task_id=?""", (now_iso, row["task_id"]),
                    )
                    self.log(db, row["task_id"], "dead_letter_operator", "quarantined",
                             f"exhausted {retries + 1} attempts")
                    quarantined += 1

            # A workflow is a DAG because dependencies can only reference already-created tasks.
            for row in db.execute(
                "SELECT task_id,depends_on_json FROM workforce_tasks WHERE status='blocked'"
            ).fetchall():
                deps = json.loads(row["depends_on_json"])
                states = [db.execute(
                    """SELECT t.status,r.receipt_id FROM workforce_tasks t
                       LEFT JOIN task_receipts r ON r.task_id=t.task_id
                       WHERE t.task_id=?""", (task_id,)
                ).fetchone() for task_id in deps]
                if any(x is None or x["status"] in ("dead_letter", "expired") for x in states):
                    db.execute(
                        "UPDATE workforce_tasks SET status='dead_letter',updated_at=? WHERE task_id=?",
                        (now_iso, row["task_id"]),
                    )
                    self.log(db, row["task_id"], "dag_advancer", "quarantined",
                             "prerequisite task unavailable or dead_letter")
                    quarantined += 1
                elif all(x["status"] == "verified_complete" and x["receipt_id"] for x in states):
                    db.execute(
                        """UPDATE workforce_tasks SET status='queued',next_eligible_at=?,
                           updated_at=? WHERE task_id=?""",
                        (now_iso, now_iso, row["task_id"]),
                    )
                    self.log(db, row["task_id"], "dag_advancer", "released",
                             "all prerequisite receipts verified")
                    released += 1
        return {"requeued": requeued, "quarantined": quarantined, "released": released}

    async def run_forever(self) -> None:
        self._stop_event = asyncio.Event()
        while not self._stop_event.is_set():
            try:
                await asyncio.to_thread(self.reconcile_once)
                if self.orchestrator is not None:
                    await asyncio.to_thread(self.orchestrator.retry_due)
            except Exception as exc:
                # The supervisor must keep running and record the actual error type.
                self.store.event("workforce.operator_failure", {"type": type(exc).__name__})
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.tick_seconds)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()

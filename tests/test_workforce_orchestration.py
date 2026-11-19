"""Typed contracts and deterministic state transitions are BRAINSTEM native invariants."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from brainstem.runtime.operators import (
    AgenticContractRegistry, ContractViolationError, WorkforceOperatorSupervisor,
)
from brainstem.runtime.store import StateStore
from brainstem.runtime.workforce_awareness import OperationalAwareness, _sanitize_error_message
from brainstem.runtime.workforce_orchestration import (
    OrchestrationError, WorkforceOrchestrator, canonical, digest,
)


def _runtime(tmp_path):
    store = StateStore(tmp_path / "orchestration.db", tmp_path / "events.jsonl")
    aware = OperationalAwareness(store)
    engine = WorkforceOrchestrator(store, aware)
    return store, aware, engine


def _emit_inventory(online=True, *, timestamp=None):
    at = timestamp or datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": "kindred.workforce.inventory.v1",
        "source": "kindred_emit_core", "observed_at": at,
        "workers": [{
            "worker_id": "worker-foundation.signal-aabbcc",
            "kind": "signal_lane", "lane": "foundation.signal",
            "status": "online" if online else "not_confirmed_online",
            "last_seen": at, "processed_signals": 1,
            "capabilities": ["signal_receive", "runtime.snapshot", "signal.deliver"],
        }],
        "registered_agents": [{"agent_id": "declared-only"}],
        "summary": {"configured_lane_definitions": 14, "registered_agent_records": 1},
    }


def _signed_receipt(task, monkeypatch, *, output=None, tamper=False):
    monkeypatch.setenv("KINDRED_INTERNAL_SERVICE_KEY", "integration-secret")
    output = output or {
        "foundation_ready": True, "lane_definitions": 18,
        "online_lane_workers": 1, "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    receipt = {
        "schema_version": "kindred.workforce.execution.receipt.v1",
        "task_id": task["task_id"],
        "worker_id": task["assigned_worker_id"],
        "lane": "foundation.signal",
        "action": task["required_capability"],
        "status": "completed", "payload_sha256": task["payload_sha256"],
        "output": output, "completed_at": datetime.now(timezone.utc).isoformat(),
        "verification": "emit_local_lane_worker_execution",
        "external_agent_execution_verified": False,
    }
    receipt["signature"] = hmac.new(
        b"integration-secret", canonical(receipt), hashlib.sha256
    ).hexdigest()
    if tamper:
        receipt["output"]["foundation_ready"] = False
    return receipt


def test_contracts_are_version_immutable_and_prelease_input_typed(tmp_path, monkeypatch):
    store, awareness, engine = _runtime(tmp_path)
    contracts = engine.contracts.list_contracts()
    assert {"signal.deliver@v1", "runtime.snapshot@v1"} <= {
        x["contract_id"] for x in contracts
    }
    with pytest.raises(ContractViolationError, match="immutable"):
        engine.contracts.register_contract(
            contract_id="signal.deliver@v1", capability="signal.deliver",
            version="v1", input_schema={"type": "object"},
            output_schema={"type": "object"}, max_lease_seconds=60, max_retries=2,
        )
    with pytest.raises(OrchestrationError) as exc:
        engine.dispatch(
            idempotency_key="invalid-input-01", contract_id="signal.deliver@v1",
            payload={"arbitrary_shell": "rm -rf /"},
        )
    assert exc.value.status_code == 422
    assert store.query("SELECT task_id FROM workforce_tasks") == []


def test_rejects_declared_agents_without_live_worker_heartbeats(tmp_path):
    _, awareness, engine = _runtime(tmp_path)
    with pytest.raises(OrchestrationError):
        engine.dispatch(idempotency_key="unsupported-payload",
                        contract_id="unknown@v1", payload={})
    pending = engine.dispatch(
        idempotency_key="only-registered-agents",
        contract_id="runtime.snapshot@v1", payload={},
    )
    assert pending["status"] == "queued"
    assert pending["assigned_worker_id"] is None
    assert awareness.overview()["summary"]["online_workers"] == 0


def test_verified_receipt_bound_to_worker_task_and_output_schema(tmp_path, monkeypatch):
    _, aware, engine = _runtime(tmp_path)
    aware.ingest_emit(_emit_inventory())
    monkeypatch.setattr(engine, "_request_emit", lambda path, payload=None, **_: (
        None if payload is None else _signed_receipt(engine.task(payload["task_id"]), monkeypatch)
    ))
    first = engine.dispatch(
        idempotency_key="verified-snapshot-01",
        contract_id="runtime.snapshot@v1", payload={},
    )
    assert first["status"] == "verified_complete"
    assert first["verified_receipt"]["worker_id"] == first["assigned_worker_id"]
    second = engine.dispatch(
        idempotency_key="verified-snapshot-01",
        contract_id="runtime.snapshot@v1", payload={},
    )
    assert first["task_id"] == second["task_id"]
    assert len(engine.summary()["verified_outcomes"]) == 1
    assert engine.awareness.overview()["summary"]["registered_emit_agent_records"] == 1


def test_bad_output_schema_never_commits_receipt(tmp_path, monkeypatch):
    _, aware, engine = _runtime(tmp_path)
    aware.ingest_emit(_emit_inventory())
    def fake_request(path, payload=None, **kwargs):
        if payload is None:
            return None
        t = engine.task(payload["task_id"])
        return _signed_receipt(t, monkeypatch, output={
            "foundation_ready": "not a boolean", "lane_definitions": 18,
            "online_lane_workers": 1, "captured_at": datetime.now(timezone.utc).isoformat(),
        })
    monkeypatch.setattr(engine, "_request_emit", fake_request)
    with pytest.raises(OrchestrationError, match="output violates"):
        engine.dispatch(
            idempotency_key="invalid-receipt-schema-01",
            contract_id="runtime.snapshot@v1", payload={},
        )
    assert engine.summary()["verified_outcomes"] == []
    assert engine.store.query("SELECT status FROM workforce_tasks")[0]["status"] == "failed"


def test_tampered_hmac_never_commits_receipt(tmp_path, monkeypatch):
    _, aware, engine = _runtime(tmp_path)
    aware.ingest_emit(_emit_inventory())
    def fake_request(path, payload=None, **kwargs):
        if payload is None:
            return None
        return _signed_receipt(engine.task(payload["task_id"]), monkeypatch, tamper=True)
    monkeypatch.setattr(engine, "_request_emit", fake_request)
    with pytest.raises(OrchestrationError, match="signature mismatch"):
        engine.dispatch(
            idempotency_key="tampered-receipt-01",
            contract_id="runtime.snapshot@v1", payload={},
        )
    assert engine.summary()["verified_outcomes"] == []


def test_operator_backoff_then_quarantine(tmp_path, monkeypatch):
    store, aware, engine = _runtime(tmp_path)
    aware.ingest_emit(_emit_inventory())
    def fail_request(path, payload=None, **kwargs):
        if payload is None:
            return None
        raise OrchestrationError(502, "worker temporarily unavailable")
    monkeypatch.setattr(engine, "_request_emit", fail_request)
    with pytest.raises(OrchestrationError):
        engine.dispatch(
            idempotency_key="retry-failure-01", contract_id="runtime.snapshot@v1",
            payload={},
        )
    operator = WorkforceOperatorSupervisor(store)
    result = operator.reconcile_once()
    assert result["requeued"] == 1
    row = store.query("SELECT * FROM workforce_tasks")[0]
    assert row["status"] == "queued"
    # Deterministically exhaust the remaining retry budget by driving the actual state machine.
    for attempt in (2, 3):
        with store.connect() as db:
            db.execute(
                """UPDATE workforce_tasks SET status='failed',attempt_count=?,
                   next_eligible_at=? WHERE task_id=?""",
                (attempt, datetime.now(timezone.utc).isoformat(), row["task_id"]),
            )
        counts = operator.reconcile_once()
    assert counts["quarantined"] == 1
    assert store.query("SELECT status FROM workforce_tasks")[0]["status"] == "dead_letter"
    assert store.query(
        "SELECT * FROM operator_audit_log WHERE action='quarantined'"
    )


def test_future_snapshot_and_transaction_rollback(tmp_path, monkeypatch):
    store, aware, engine = _runtime(tmp_path)
    aware.ingest_emit(_emit_inventory())
    future = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
    with pytest.raises(ValueError, match="stale or invalid"):
        aware.ingest_emit(_emit_inventory(timestamp=future))
    assert aware.overview()["summary"]["online_workers"] == 1
    def explode(db, records):
        raise RuntimeError("intentional transaction fault")
    monkeypatch.setattr(aware, "_upsert_with_connection", explode)
    with pytest.raises(RuntimeError, match="intentional"):
        aware.ingest_emit(_emit_inventory(online=False))
    assert aware.overview()["summary"]["online_workers"] == 1


def test_transport_error_does_not_persist_internal_key(tmp_path, monkeypatch):
    _, aware, engine = _runtime(tmp_path)
    secret = "internal-signing-secret-NO-LEAK"
    monkeypatch.setenv("KINDRED_INTERNAL_SERVICE_KEY", secret)
    result = aware._sync_failure(f"Invalid header value b'{secret}'")
    assert secret not in result["error"]
    assert secret not in str(aware.overview()["sources"])


def test_dag_releases_only_after_verified_predecessor(tmp_path, monkeypatch):
    store, aware, engine = _runtime(tmp_path)
    aware.ingest_emit(_emit_inventory())
    parent = engine.dispatch(
        idempotency_key="dag-parent-0001", contract_id="runtime.snapshot@v1", payload={}
    )
    assert parent["status"] == "leased" or parent["status"] == "queued" or parent["status"] == "failed"
    child = engine.dispatch(
        idempotency_key="dag-child-0001", contract_id="signal.deliver@v1",
        payload={"signal": "dependent"}, depends_on=[parent["task_id"]],
    )
    assert child["status"] == "blocked"
    operator = WorkforceOperatorSupervisor(store)
    assert operator.reconcile_once()["released"] == 0
    with store.connect() as db:
        db.execute(
            "UPDATE workforce_tasks SET status='verified_complete' WHERE task_id=?",
            (parent["task_id"],),
        )
    assert operator.reconcile_once()["released"] == 1
    assert engine.task(child["task_id"])["status"] == "queued"

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
    # No worker is initially online: dependency creation must never dispatch itself.
    parent = engine.dispatch(
        idempotency_key="dag-parent-0001", contract_id="runtime.snapshot@v1", payload={}
    )
    assert parent["status"] == "queued"
    child = engine.dispatch(
        idempotency_key="dag-child-0001", contract_id="signal.deliver@v1",
        payload={"signal": "dependent"}, depends_on=[parent["task_id"]],
    )
    assert child["status"] == "blocked"
    operator = WorkforceOperatorSupervisor(store)
    assert operator.reconcile_once()["released"] == 0
    # A forged status without a matching receipt must not release dependencies.
    with store.connect() as db:
        db.execute(
            "UPDATE workforce_tasks SET status='verified_complete' WHERE task_id=?",
            (parent["task_id"],),
        )
    assert operator.reconcile_once()["released"] == 0
    # The worker must exist before a task lease can reference its composite
    # (source, worker_id) foreign key. Ingest an authenticated snapshot first.
    aware.ingest_emit(_emit_inventory())
    with store.connect() as db:
        db.execute(
            """UPDATE workforce_tasks SET status='leased',assigned_source=?,
               assigned_worker_id=?,lease_expires_at=? WHERE task_id=?""",
            ("kindred_emit_core", "worker-foundation.signal-aabbcc",
             (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(),
             parent["task_id"]),
        )
    receipt = _signed_receipt(engine.task(parent["task_id"]), monkeypatch)
    assert engine._commit_receipt(parent["task_id"], receipt)["status"] == "verified_complete"
    assert operator.reconcile_once()["released"] == 1
    assert engine.task(child["task_id"])["status"] == "queued"


def test_contract_retirement_preserves_old_receipt_validator(tmp_path):
    store, aware, engine = _runtime(tmp_path)
    contract_id = "signal.deliver@v1"
    original = engine.contracts.contract(contract_id)
    retired = engine.contracts.deactivate_contract(contract_id)
    assert retired["active"] == 0
    with pytest.raises(ContractViolationError, match="active contract not found"):
        engine.contracts.validate_input(contract_id, {"signal": "no new dispatch"})
    # The immutable original schema must still validate old, signed receipts.
    engine.contracts.validate_output(contract_id, {
        "lane": "task.signal", "signal_sha256": "0" * 64, "processed_count_after": 1,
    })
    assert engine.contracts.contract(contract_id, require_active=False)["created_at"] == original["created_at"]
    recovered = AgenticContractRegistry(store)
    assert recovered.contract(contract_id, require_active=False)["active"] == 0


def test_cached_schema_validator_is_reused(tmp_path):
    _, _, engine = _runtime(tmp_path)
    engine.contracts.validate_input("signal.deliver@v1", {"signal": "hello"})
    engine.contracts.validate_input("signal.deliver@v1", {"signal": "world"})
    info = engine.contracts._validator.cache_info()
    assert info.hits >= 1


def test_wal_busy_timeout_configuration(tmp_path):
    store, _, _ = _runtime(tmp_path)
    with store.connect() as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert db.execute("PRAGMA synchronous").fetchone()[0] == 1
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] >= 10000
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_api_contract_registration_and_access_control(tmp_path, monkeypatch):
    from brainstem.runtime.app import build_app
    from fastapi.testclient import TestClient
    monkeypatch.setenv("BRAINSTEM_AWARENESS_KEY", "orchestration-local-test-key")
    app = build_app(database=tmp_path / "api.db")
    with TestClient(app) as client:
        denied = client.get("/contracts")
        assert denied.status_code == 401
        hdr = {"X-Brainstem-Awareness-Key": "orchestration-local-test-key"}
        listed = client.get("/contracts", headers=hdr)
        assert listed.status_code == 200
        assert any(c["contract_id"] == "runtime.snapshot@v1" for c in listed.json())
        invalid = client.post("/orchestration/dispatch", headers=hdr, json={
            "idempotency_key": "contract-test-invalid",
            "contract_id": "signal.deliver@v1",
            "payload": {"signal": 78},
        })
        assert invalid.status_code == 422
        duplicate = client.post("/contracts", headers=hdr, json={
            "contract_id": "runtime.snapshot@v1", "capability": "runtime.snapshot",
            "version": "v1", "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        })
        assert duplicate.status_code == 422


def test_expired_lease_reclaimed_with_backoff_and_audit(tmp_path):
    store, aware, engine = _runtime(tmp_path)
    row = engine.dispatch(
        idempotency_key="lease-expiration-0001",
        contract_id="runtime.snapshot@v1", payload={},
    )
    with store.connect() as db:
        db.execute(
            """UPDATE workforce_tasks
               SET status='leased',attempt_count=1,lease_expires_at=?
               WHERE task_id=?""",
            ((datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(), row["task_id"]),
        )
    op = WorkforceOperatorSupervisor(store)
    state = op.reconcile_once()
    assert state["requeued"] == 1
    current = engine.task(row["task_id"])
    assert current["status"] == "queued"
    assert datetime.fromisoformat(current["next_eligible_at"]) > datetime.now(timezone.utc)
    assert store.query(
        "SELECT * FROM operator_audit_log WHERE task_id=? AND action='requeued'",
        (row["task_id"],),
    )
    assert op.reconcile_once()["requeued"] == 0


def test_deactivated_contract_can_no_longer_dispatch(tmp_path):
    _, _, engine = _runtime(tmp_path)
    engine.contracts.deactivate_contract("runtime.snapshot@v1")
    with pytest.raises(OrchestrationError) as exc:
        engine.dispatch(
            idempotency_key="retired-contract-0001",
            contract_id="runtime.snapshot@v1", payload={},
        )
    assert exc.value.status_code == 422


def _poecl_receipt(task, monkeypatch, *, corrupt_proof=False):
    from brainstem.runtime.causal_verification import DOMAIN, _canonical, _merkle_root
    receipt = _signed_receipt(task, monkeypatch)
    receipt.pop("signature")
    events = [
        {"event": "queue.dequeued", "worker_id": receipt["worker_id"]},
        {"event": "operator.completed", "capability_uri": receipt["action"]},
        {"event": "audit.persisted", "task_id": receipt["task_id"]},
    ]
    proof = {
        "schema_version": "kindred.poecl.process_trace.v1",
        "sequence": 1,
        "prev_chain_hash": "0" * 64,
        "task_id": receipt["task_id"],
        "worker_id": receipt["worker_id"],
        "capability_uri": receipt["action"],
        "outcome": receipt["status"],
        "input_sha256": receipt["payload_sha256"],
        "output_sha256": hashlib.sha256(_canonical(receipt["output"])).hexdigest(),
        "trace_events": events,
        "trace_merkle_root": _merkle_root(events),
        "elapsed_ns": 45000,
        "energy_joules_est": None,
        "energy_source": "unmeasured",
        "attestation_level": "emit_local_process_instrumentation",
    }
    proof["chain_hash"] = hashlib.sha256(DOMAIN + _canonical(proof)).hexdigest()
    if corrupt_proof:
        proof["trace_merkle_root"] = "a" * 64
    receipt["causal_proof"] = proof
    receipt["signature"] = hmac.new(
        b"integration-secret", _canonical(receipt), hashlib.sha256
    ).hexdigest()
    return receipt


def test_v2_causal_contract_accepts_bound_attested_receipt(tmp_path, monkeypatch):
    _, aware, engine = _runtime(tmp_path)
    aware.ingest_emit(_emit_inventory())
    monkeypatch.setattr(engine, "_request_emit", lambda path, payload=None, **_: (
        None if payload is None else _poecl_receipt(
            engine.task(payload["task_id"]), monkeypatch
        )
    ))
    task = engine.dispatch(
        idempotency_key="poecl-v2-happy-001",
        contract_id="runtime.snapshot@v2", payload={},
    )
    assert task["status"] == "verified_complete"
    assert task["verified_receipt"]["causal_proof"]["sequence"] == 1
    assert engine.summary()["verified_outcomes"][0]["causal_chain_hash"] == (
        task["verified_receipt"]["causal_proof"]["chain_hash"]
    )


def test_v2_causal_contract_rejects_missing_and_invalid_proofs(tmp_path, monkeypatch):
    _, aware, engine = _runtime(tmp_path)
    aware.ingest_emit(_emit_inventory())
    monkeypatch.setattr(engine, "_request_emit", lambda path, payload=None, **_: (
        None if payload is None else _signed_receipt(
            engine.task(payload["task_id"]), monkeypatch
        )
    ))
    with pytest.raises(OrchestrationError, match="causal receipt"):
        engine.dispatch(
            idempotency_key="poecl-no-proof-001",
            contract_id="runtime.snapshot@v2", payload={},
        )
    assert engine.summary()["verified_outcomes"] == []

    def forged(path, payload=None, **kwargs):
        if payload is None:
            return None
        return _poecl_receipt(
            engine.task(payload["task_id"]), monkeypatch, corrupt_proof=True
        )
    monkeypatch.setattr(engine, "_request_emit", forged)
    with pytest.raises(OrchestrationError, match="causal receipt"):
        engine.dispatch(
            idempotency_key="poecl-bad-root-002",
            contract_id="runtime.snapshot@v2", payload={},
        )
    assert engine.summary()["verified_outcomes"] == []


def test_kacf_dispatch_prepares_inert_fork_even_without_live_worker(tmp_path):
    store, aware, engine = _runtime(tmp_path)
    task = engine.dispatch(
        idempotency_key="kacf-queued-fork-001", contract_id="runtime.snapshot@v2",
        payload={},
    )
    assert task["status"] == "queued" and task["assigned_worker_id"] is None
    snapshot = engine.fabric.summary()
    assert len(snapshot["forks"]) == 1
    assert snapshot["forks"][0]["task_id"] == task["task_id"]
    assert snapshot["forks"][0]["status"] == "prepared"
    assert snapshot["forks"][0]["dispatch_policy"] == "single"
    assert snapshot["energy_source"] == "unmeasured"
    assert snapshot["hcm_recovery_queue"] == []


def test_kacf_v2_causal_receipt_collapses_once_and_updates_measured_proxy(tmp_path, monkeypatch):
    store, aware, engine = _runtime(tmp_path)
    aware.ingest_emit(_emit_inventory())
    monkeypatch.setattr(engine, "_request_emit", lambda path, payload=None, **_: (
        None if payload is None else _poecl_receipt(
            engine.task(payload["task_id"]), monkeypatch
        )
    ))
    result = engine.dispatch(
        idempotency_key="kacf-v2-collapse-001",
        contract_id="runtime.snapshot@v2", payload={},
    )
    assert result["status"] == "verified_complete"
    fork = store.query("SELECT * FROM kacf_forks WHERE task_id=?", (result["task_id"],))[0]
    assert fork["status"] == "collapsed" and fork["outcome"] == "succeeded"
    assert fork["receipt_hash"] is not None
    summary = engine.summary()
    assert summary["kacf"]["metabolics"][0]["samples"] == 1
    assert summary["kacf"]["metabolics"][0]["joules"] is None
    # The dispatch idempotency key must not double-count the signed outcome.
    replay = engine.dispatch(
        idempotency_key="kacf-v2-collapse-001",
        contract_id="runtime.snapshot@v2", payload={},
    )
    assert replay["task_id"] == result["task_id"]
    assert engine.fabric.summary()["metabolics"][0]["samples"] == 1


def test_kacf_invalid_signed_outcome_cannot_collapse_fork(tmp_path, monkeypatch):
    store, aware, engine = _runtime(tmp_path)
    aware.ingest_emit(_emit_inventory())
    monkeypatch.setattr(engine, "_request_emit", lambda path, payload=None, **_: (
        None if payload is None else _poecl_receipt(
            engine.task(payload["task_id"]), monkeypatch, corrupt_proof=True
        )
    ))
    with pytest.raises(OrchestrationError, match="causal receipt"):
        engine.dispatch(
            idempotency_key="kacf-bad-proof-001",
            contract_id="runtime.snapshot@v2", payload={},
        )
    forks = store.query("SELECT status FROM kacf_forks")
    assert len(forks) == 1 and forks[0]["status"] == "prepared"
    assert engine.fabric.summary()["metabolics"] == []


def test_kacf_hcm_incident_only_after_terminal_task(tmp_path):
    store, aware, engine = _runtime(tmp_path)
    task = engine.dispatch(
        idempotency_key="kacf-hcm-incident-001",
        contract_id="signal.deliver@v2", payload={"signal": "probe"},
    )
    assert engine.fabric.reconcile_terminal_incidents() == 0
    with store.connect() as db:
        db.execute(
            "UPDATE workforce_tasks SET status='dead_letter',last_error='test exhausted' WHERE task_id=?",
            (task["task_id"],),
        )
    assert engine.fabric.reconcile_terminal_incidents() == 1
    assert engine.fabric.reconcile_terminal_incidents() == 0
    assert engine.fabric.summary()["hcm_recovery_queue"][0]["capability"] == "signal.deliver"

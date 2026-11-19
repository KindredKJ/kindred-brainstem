"""Native awareness survives restarts and never equates registration with liveness."""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from brainstem.runtime.app import WorkforceObservationRequest, build_app
from brainstem.runtime.store import StateStore
from brainstem.runtime.workforce_awareness import OperationalAwareness


def _store(tmp_path):
    return StateStore(tmp_path / "brainstem.db", tmp_path / "events.jsonl")


def _emit_snapshot():
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": "kindred.workforce.inventory.v1",
        "source": "kindred_emit_core",
        "observed_at": now,
        "workers": [{
            "worker_id": "worker-task.signal-a01",
            "source": "kindred_emit_core",
            "kind": "signal_lane",
            "lane": "task.signal",
            "status": "online",
            "last_seen": now,
            "processed_signals": 3,
            "failure_count": 0,
            "external_action_verified": False,
        }],
        "registered_agents": [
            {"agent_id": "intake_agent", "registration_status": "declared_not_observed"}
        ],
        "summary": {
            "configured_lane_definitions": 14,
            "registered_agent_records": 1,
            "observed_agent_processes": 0,
        },
    }


def test_emit_snapshot_preserves_worker_vs_registration_distinction(tmp_path):
    awareness = OperationalAwareness(_store(tmp_path))
    result = awareness.ingest_emit(_emit_snapshot())
    assert result["summary"]["online_workers"] == 1
    assert result["summary"]["observed_worker_records"] == 1
    assert result["summary"]["configured_emit_lane_definitions"] == 14
    assert result["summary"]["registered_emit_agent_records"] == 1
    assert result["summary"]["independently_verified_external_workers"] == 0


def test_brainstem_owns_worker_state_across_restart(tmp_path):
    awareness = OperationalAwareness(_store(tmp_path))
    awareness.observe("kindred_native", "worker-001", "research", "online")
    recovered = OperationalAwareness(_store(tmp_path))
    assert recovered.overview()["summary"]["online_workers"] == 1
    with recovered.store.connect() as db:
        db.execute(
            "UPDATE workforce_observations SET observed_at='2020-01-01T00:00:00+00:00'"
        )
    assert recovered.overview()["summary"]["online_workers"] == 0
    assert recovered.overview()["workers"][0]["status"] == "stale"


def test_no_emit_dependency_to_accept_local_worker_observations(tmp_path, monkeypatch):
    monkeypatch.delenv("KINDRED_EMIT_CORE_URL", raising=False)
    monkeypatch.delenv("KINDRED_INTERNAL_SERVICE_KEY", raising=False)
    awareness = OperationalAwareness(_store(tmp_path))
    assert awareness.sync_emit()["status"] == "not_configured"
    observed = awareness.observe("kindred_native", "worker-002", "agent", "busy")
    assert observed["worker_id"] == "worker-002"
    assert awareness.overview()["summary"]["online_workers"] == 1


def test_rejects_duplicate_emit_worker_ids(tmp_path):
    awareness = OperationalAwareness(_store(tmp_path))
    payload = _emit_snapshot()
    payload["workers"].append(dict(payload["workers"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        awareness.ingest_emit(payload)


def test_authenticated_direct_observations(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAINSTEM_AWARENESS_KEY", "unit-test-awareness-key")
    app = build_app(database=tmp_path / "api.db")
    route = next(
        r.endpoint for r in app.routes if getattr(r, "path", None) == "/awareness/workers/observe"
    )
    request = WorkforceObservationRequest(
        source="kindred_native", worker_id="worker-003",
        kind="execution", status="online",
    )
    with pytest.raises(HTTPException) as denied:
        route(request, x_brainstem_awareness_key="wrong")
    assert denied.value.status_code == 401
    result = route(request, x_brainstem_awareness_key="unit-test-awareness-key")
    assert result["worker_id"] == "worker-003"
    summary_route = next(
        r.endpoint for r in app.routes if getattr(r, "path", None) == "/awareness/workers"
    )
    assert summary_route()["summary"]["online_workers"] == 1
    world_route = next(
        r.endpoint for r in app.routes if getattr(r, "path", None) == "/world"
    )
    assert world_route()["operational_awareness"]["summary"]["online_workers"] == 1

"""Real native BRAINSTEM DCML cognition, no generated-text provider required."""
import json

import pytest

from brainstem.model.core import BrainstemModel
from brainstem.runtime.app import (
    SessionRequest, NativeDCMLCycleRequest, build_app,
)
from brainstem.runtime.service import RuntimeService
from brainstem.runtime.store import StateStore


def route(app, path):
    return next(r.endpoint for r in app.routes if getattr(r, "path", None) == path)


@pytest.fixture()
def runtime(tmp_path):
    # No healthy adapter, no generative model, no external network.
    return RuntimeService(
        StateStore(tmp_path / "brainstem-native.db", tmp_path / "native-events.jsonl"),
        adapters={"unavailable": UnavailableAdapter()},
    )


class UnavailableAdapter:
    identity = "UNAVAILABLE_TEST_INSTRUMENT"

    def capabilities(self):
        return set()

    def health(self):
        from brainstem.adapters.models.base import ModelHealth
        return ModelHealth("NOT_CONFIGURED", "No external inference")

    def generate(self, messages):
        raise AssertionError("Native DCML must never invoke external generation")


def test_native_session_and_cycle_without_inference_adapter(runtime):
    app = build_app(service=runtime)
    session = route(app, "/dcml/native-sessions")(SessionRequest())
    assert session["model"] == "brainstem-native"
    result = route(app, "/dcml/native-cycle")(
        NativeDCMLCycleRequest(
            session_id=session["id"],
            message="Research verified customer requirements",
            context={"wing": "research", "mission_id": "company-mission-one"},
        )
    )
    assert result["schema"] == "kindred.brainstem.native-dcml.v1"
    assert result["model_identity"] == "KINDRED-BRAINSTEM"
    assert result["session_id"] == session["id"]
    assert result["strategy"]["id"]
    assert result["prediction"]["id"]
    assert result["counterfactual"]["prediction_id"] == result["prediction"]["id"]
    assert result["evidence_id"]
    assert result["external_instrument_used"] is False
    assert result["language_generation_performed"] is False
    assert result["external_outcome_verified"] is False
    assert result["learning_status"] == "not_evaluated"
    assert result["inference_mode"] == "native_structured_policy"
    assert runtime.model.inspect_state().revision == result["state_revision"]
    assert runtime.store.session(session["id"])["model"] == "brainstem-native"


def test_five_wings_share_one_native_cognitive_identity(runtime):
    wings = ("research", "platform", "products", "ventures", "fleet")
    sessions = []
    revisions = []
    for wing in wings:
        session = runtime.create_native_session(repository=f"continuum:{wing}")
        result = runtime.native_cycle(
            session["id"],
            f"Plan evidence gathering in the {wing} wing",
            context={"wing": wing, "mission_id": "mission-1"},
        )
        sessions.append(session["id"])
        revisions.append(result["state_revision"])
        assert result["model_identity"] == "KINDRED-BRAINSTEM"
        assert result["inference_mode"] == "native_structured_policy"
    assert len(set(sessions)) == 5
    assert len(set(revisions)) == 5
    assert revisions == sorted(revisions)
    assert len(runtime.store.query("SELECT id FROM predictions")) == 5
    assert len(runtime.store.query("SELECT id FROM experiences")) == 5
    assert len(runtime.store.query("SELECT id FROM evidence")) == 5
    assert len(runtime.store.query("SELECT id FROM telemetry")) == 0


def test_native_cognition_persists_across_process_reopen(runtime):
    session = runtime.create_native_session()
    first = runtime.native_cycle(session["id"], "Use existing evidence")
    reopened = RuntimeService(
        StateStore(runtime.store.path, runtime.store.audit_path),
        adapters={"unavailable": UnavailableAdapter()},
    )
    assert reopened.model.inspect_state().revision == first["state_revision"]
    second = reopened.native_cycle(session["id"], "Verify an observed outcome")
    assert second["state_revision"] > first["state_revision"]
    assert reopened.store.session(session["id"])["model"] == "brainstem-native"


def test_recall_before_current_experience_is_recorded(runtime):
    session = runtime.create_native_session()
    first = runtime.native_cycle(session["id"], "Unique newly observed fact")
    assert first["recalled"]["experiences"] == 0
    second = runtime.native_cycle(session["id"], "Unique newly observed fact")
    assert second["recalled"]["experiences"] >= 1


def test_no_fictional_customer_success_from_strategy_prediction(runtime):
    session = runtime.create_native_session()
    result = runtime.native_cycle(session["id"], "Make Kindred Cloud profitable")
    rows = runtime.store.query("SELECT result FROM experiences")
    data = json.loads(rows[0]["result"])
    assert data["status"] == "prediction_pending_verification"
    assert result["external_outcome_verified"] is False
    assert len(runtime.store.query("SELECT id FROM evaluations")) == 0
    assert len(runtime.store.query("SELECT id FROM learning_proposals")) == 0


def test_native_session_not_confused_with_provider_session(runtime):
    nonnative = runtime.store.create_session("unavailable")
    with pytest.raises(ValueError, match="not a native"):
        runtime.native_cycle(nonnative["id"], "Should not run")
    assert runtime.store.query("SELECT id FROM experiences") == []


def test_native_api_rejects_external_model_attachment(runtime):
    app = build_app(service=runtime)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        route(app, "/dcml/native-sessions")(SessionRequest(model="unavailable"))
    assert exc.value.status_code == 422


def test_native_bad_input_rejected_without_new_experience(runtime):
    session = runtime.create_native_session()
    with pytest.raises(ValueError):
        runtime.native_cycle(session["id"], " ")
    with pytest.raises(ValueError):
        runtime.native_cycle(session["id"], "task", {"large": "x" * 8500})
    assert runtime.store.query("SELECT id FROM experiences") == []

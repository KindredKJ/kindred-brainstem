import inspect
import json

import pytest

from brainstem.adapters.models.base import Generation, ModelAdapter, ModelHealth
from brainstem.model.core import BrainstemModel
from brainstem.model.schemas import StrategyCandidate
from brainstem.runtime.service import RuntimeService
from brainstem.runtime.store import StateStore


class CapturingInstrument(ModelAdapter):
    identity = "SIMULATED_SPECIALIST"

    def __init__(self):
        self.messages = []

    def capabilities(self):
        return {"generate"}

    def health(self):
        return ModelHealth("HEALTHY", "SIMULATED test probe")

    def generate(self, messages):
        self.messages = messages
        return Generation(
            "clean assistant answer",
            self.identity,
            {"total_tokens": 7},
            {"commands": ["safe-command"], "execution_events": [{"type": "completed"}]},
        )


class FailingInstrument(CapturingInstrument):
    identity = "SIMULATED_FAILURE"

    def generate(self, messages):
        self.messages = messages
        raise RuntimeError("SIMULATED instrument failure")


def make_model(tmp_path, instrument=None):
    adapter = instrument or CapturingInstrument()
    store = StateStore(tmp_path / "state.db", tmp_path / "audit.jsonl")
    model = BrainstemModel(store, {"specialist": adapter})
    session = store.create_session("specialist")
    return model, store, session, adapter


def learned_strategy_payload(name="approved_strategy"):
    return {
        "strategy": StrategyCandidate(
            id="KSTR-APPROVED",
            name=name,
            description="Founder-approved high-evidence procedure",
            expected_utility=0.98,
            risk=0.05,
            confidence=0.95,
            source="candidate_learning",
        ).model_dump()
    }


def activate(model, payload=None):
    learning_id = model.learn(
        "strategy", payload or learned_strategy_payload(), ["test-evidence"]
    )
    model.evaluate_learning(learning_id, 0.95, ["evaluation-evidence"])
    model.approve_learning(learning_id, "Kindred Jermaine Cox")
    model.promote_learning(learning_id)
    model.activate_learning(learning_id)
    return learning_id


def test_identity_and_cognitive_state_survive_model_restart(tmp_path):
    model, store, session, _ = make_model(tmp_path)
    result = model.cognitive_cycle(session["id"], "retain this", "specialist")
    reopened = BrainstemModel(
        StateStore(store.path, tmp_path / "audit.jsonl"),
        {"specialist": CapturingInstrument()},
    )
    state = reopened.inspect_state()
    assert state.identity == "Kindred BRAINSTEM"
    assert state.revision == result.state_revision
    assert result.cycle_id in json.dumps(store.query("SELECT content FROM evidence"))


def test_attached_thread_receives_brainstem_owned_context_and_separate_telemetry(
    tmp_path,
):
    model, store, session, adapter = make_model(tmp_path)
    result = model.cognitive_cycle(
        session["id"], "analyze repository", "specialist", {"repo": "kindred"}
    )
    framing = json.loads(adapter.messages[0]["content"])
    assert framing["owner"] == "Kindred BRAINSTEM"
    assert framing["instrument_role"] == "subordinate specialist"
    assert framing["permissions"] == ["generate_response"]
    assert result.response == "clean assistant answer"
    assert "safe-command" not in result.response
    telemetry = store.query(
        "SELECT * FROM telemetry WHERE id=?", (result.telemetry_id,)
    )[0]
    assert json.loads(telemetry["commands"]) == ["safe-command"]


def test_prediction_error_proposes_learning(tmp_path):
    model, _, _, _ = make_model(tmp_path)
    strategy = model.reason("question", model.recall("question"))[0]
    prediction, _ = model.simulate(strategy, "question")
    comparison = model.observe_outcome(prediction.id, "harmful_outcome")
    assert comparison["prediction_error"] > 0
    proposal = model.learning(comparison["learning_proposal_id"])[0]
    assert proposal["status"] == "PROPOSED"
    assert proposal["kind"] == "prediction_error"


def test_learning_requires_approval_and_approved_strategy_changes_selection(tmp_path):
    model, _, _, _ = make_model(tmp_path)
    learning_id = model.learn("strategy", learned_strategy_payload(), ["evidence"])
    model.evaluate_learning(learning_id, 0.9, ["evaluation"])
    with pytest.raises(ValueError):
        model.promote_learning(learning_id)
    with pytest.raises(PermissionError):
        model.approve_learning(learning_id, "not-founder")
    model.approve_learning(learning_id, "Kindred Jermaine Cox")
    model.promote_learning(learning_id)
    assert model.reason("x", model.recall("x"))[0].name != "approved_strategy"
    model.activate_learning(learning_id)
    selected = model.decide(model.reason("x", model.recall("x")))
    assert selected.name == "approved_strategy"


def test_rejected_learning_has_no_effect(tmp_path):
    model, _, _, _ = make_model(tmp_path)
    learning_id = model.learn(
        "strategy", learned_strategy_payload("rejected_strategy"), ["evidence"]
    )
    model.reject_learning(learning_id, "Kindred Jermaine Cox")
    assert model.learning(learning_id)[0]["status"] == "REJECTED"
    assert all(row["name"] != "rejected_strategy" for row in model.strategies())


def test_conflicting_beliefs_remain_visible(tmp_path):
    model, _, _, _ = make_model(tmp_path)
    model.add_belief("system", "status", "available", 0.8, ["probe-a"])
    model.add_belief("system", "status", "unavailable", 0.7, ["probe-b"])
    beliefs = model.beliefs()
    assert {row["object"] for row in beliefs} == {"available", "unavailable"}
    assert {row["status"] for row in beliefs} == {"CONFLICTED"}
    assert model.inspect_state().unresolved_contradictions


def test_promoted_learning_can_be_rolled_back(tmp_path):
    model, _, _, _ = make_model(tmp_path)
    learning_id = activate(model)
    assert (
        model.decide(model.reason("x", model.recall("x"))).name == "approved_strategy"
    )
    model.rollback_learning(learning_id)
    assert model.learning(learning_id)[0]["status"] == "ROLLED_BACK"
    assert (
        model.decide(model.reason("x", model.recall("x"))).name != "approved_strategy"
    )


def test_checkpoint_restores_prior_cognitive_revision(tmp_path):
    model, _, session, _ = make_model(tmp_path)
    model.cognitive_cycle(session["id"], "first", "specialist")
    checkpoint = model.checkpoint()
    expected_context = model.inspect_state().current_context
    model.cognitive_cycle(session["id"], "second", "specialist", {"changed": True})
    restored = model.rollback(checkpoint)
    assert restored.current_context == expected_context


def test_attached_failure_does_not_commit_cognitive_state(tmp_path):
    model, store, session, adapter = make_model(tmp_path, FailingInstrument())
    before = model.inspect_state()
    with pytest.raises(RuntimeError, match="SIMULATED"):
        model.cognitive_cycle(session["id"], "fail safely", "specialist")
    after = model.inspect_state()
    assert after == before
    assert store.query("SELECT status FROM telemetry")[0]["status"] == "DEGRADED"
    assert adapter.messages[0]["role"] == "system"


def test_runtime_delegates_cognition_to_model_interface(tmp_path):
    adapter = CapturingInstrument()
    store = StateStore(tmp_path / "runtime.db")
    runtime = RuntimeService(store, {"specialist": adapter})
    session = runtime.create_session("specialist")
    response = runtime.chat(session["id"], "delegate")
    assert response["response"] == "clean assistant answer"
    source = inspect.getsource(RuntimeService.chat)
    assert ".cognitive_cycle(" in source
    assert "StrategyCandidate" not in source


def test_schema_migration_preserves_existing_session(tmp_path):
    path = tmp_path / "migration.db"
    first = StateStore(path)
    session = first.create_session("legacy")
    reopened = StateStore(path)
    assert reopened.session(session["id"])["model"] == "legacy"
    assert reopened.query("SELECT version FROM schema_migrations") == [
        {"version": 1},
        {"version": 2},
        {"version": 3},
        {"version": 4},
    ]


def test_codex_ndjson_is_normalized_and_raw_events_are_telemetry(tmp_path):
    executable = tmp_path / "codex"
    executable.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then echo \'codex test\'; exit 0; fi\n'
        'echo \'{"item":{"type":"agent_message","text":"clean codex answer"}}\'\n'
        'echo \'{"type":"turn.completed","usage":{"total_tokens":9}}\'\n'
    )
    executable.chmod(0o755)
    from brainstem.adapters.models.codex import CodexAdapter

    result = CodexAdapter(str(executable), str(tmp_path)).generate(
        [{"role": "user", "content": "task"}]
    )
    assert result.text == "clean codex answer"
    assert not result.text.startswith("{")
    assert result.usage == {"total_tokens": 9}
    assert len(result.telemetry["execution_events"]) == 2


def test_reference_dataset_never_claims_weight_training(tmp_path):
    from brainstem.model.training import ReferenceDatasetBuilder

    model, store, session, _ = make_model(tmp_path)
    experience = model.perceive(session["id"], "approved example")
    store.execute(
        "UPDATE experiences SET approved_for_training=1 WHERE id=?", (experience,)
    )
    dataset = ReferenceDatasetBuilder(store).build(tmp_path / "dataset.json")
    assert dataset.parameter_training_performed is False
    assert dataset.status == "REFERENCE_ONLY"
    assert experience in dataset.evaluation_split

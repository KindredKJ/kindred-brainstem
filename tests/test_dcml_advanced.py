import pytest

from brainstem.model.dcml import DCMLLearning
from brainstem.runtime.store import StateStore


def dcml(tmp_path):
    return DCMLLearning(StateStore(tmp_path / "advanced.db"))


def approved_experience(model, index, input_state):
    exp = model.record_experience(
        session_id="s",
        mission_id="m",
        goal="verified structured repair",
        input_state=input_state,
        selected_strategy="verified_procedure",
        selected_instrument="SIMULATED_ADVANCED_TEST",
        predicted_outcome="passing_test",
        success_criteria={"expected_outcome": "passing_test"},
        privacy_classification="INTERNAL_APPROVED",
        retention_classification="LEARNING_APPROVED",
        provenance=[f"proof-{index}"],
    )
    model.observe(exp, "passing_test", 1.0)
    model.verify_experience(exp, "passing_test", {"test": f"SIMULATED-{index}"})
    model.store.execute(
        "UPDATE experiences_v2 SET status='APPROVED_FOR_LEARNING' WHERE id=?", (exp,)
    )
    return exp


def test_concept_formation_and_structural_transfer_not_keywords(tmp_path):
    model = dcml(tmp_path)
    first = approved_experience(
        model, 1, {"repository": {"files": ["a.py"], "tests": 1}}
    )
    second = approved_experience(
        model, 2, {"repository": {"files": ["b.py"], "tests": 2}}
    )
    concept = model.advanced.form_concept(
        "repository-test-repair", [first, second], ["plain prose"]
    )
    applicable = model.advanced.transfer_evaluate(
        concept,
        {"repository": {"files": ["new.py"], "tests": 4}},
        threshold=0.5,
        baseline_score=0.2,
        applied_score=0.9,
    )
    inappropriate = model.advanced.transfer_evaluate(
        concept, "repository repository same keywords only", threshold=0.5
    )
    assert applicable["applicable"] is True and applicable[
        "transfer_lift"
    ] == pytest.approx(0.7)
    assert inappropriate["applicable"] is False
    assert applicable["keyword_similarity_used"] is False


def test_causal_hypothesis_strengthens_then_rejects_with_falsification(tmp_path):
    model = dcml(tmp_path)
    hypothesis = model.advanced.create_causal_hypothesis(
        "verified procedure",
        "passing tests",
        ["task difficulty"],
        ["instrument quality"],
        0.8,
    )
    strengthened = model.advanced.intervene(
        hypothesis, "apply procedure", 0.75, ["task difficulty"], ["test-run-1"]
    )
    assert strengthened["status"] == "STRENGTHENED"
    result = strengthened
    for index in range(4):
        result = model.advanced.intervene(
            hypothesis,
            f"falsification-{index}",
            0.0,
            ["task difficulty"],
            [f"failure-{index}"],
        )
    assert result["status"] == "REJECTED"
    record = model.advanced._get("causal_hypotheses", hypothesis)["payload"]
    assert record["classification"] == "HYPOTHESIS_NOT_VERIFIED_CAUSATION"
    assert record["falsification_evidence"]


def test_counterfactual_regret_is_persisted(tmp_path):
    model = dcml(tmp_path)
    decision = model.advanced.counterfactual_decide(
        [
            {
                "strategy": "fast",
                "expected_success": 0.7,
                "expected_cost": 0.1,
                "expected_latency_ms": 10,
                "risk": 0.2,
                "reversible": True,
                "evidence_requirements": ["test"],
                "uncertainty": 0.2,
            },
            {
                "strategy": "safe",
                "expected_success": 0.8,
                "expected_cost": 0.2,
                "expected_latency_ms": 20,
                "risk": 0.05,
                "reversible": True,
                "evidence_requirements": ["test"],
                "uncertainty": 0.1,
            },
        ]
    )
    observed = model.advanced.observe_counterfactual(decision["id"], 0.4, {"fast": 0.9})
    assert observed["counterfactual_regret"] == pytest.approx(0.5)


def test_historical_calibration_changes_routing_and_no_fallback(tmp_path):
    model = dcml(tmp_path)
    model.advanced.update_model_profile(
        "model-a", "code", 0, 10, 0.1, 0.9, "passing_test"
    )
    model.advanced.update_model_profile(
        "model-b", "code", 1, 20, 0.2, 0.8, "passing_test"
    )
    candidates = [
        {
            "model_id": "model-a",
            "health": "HEALTHY",
            "privacy_classes": ["INTERNAL"],
            "cost": 0.1,
            "latency_ms": 10,
            "max_risk": 0.5,
        },
        {
            "model_id": "model-b",
            "health": "HEALTHY",
            "privacy_classes": ["INTERNAL"],
            "cost": 0.2,
            "latency_ms": 20,
            "max_risk": 0.5,
        },
    ]
    route = model.advanced.route_model("code", candidates, "INTERNAL", 0.2, 1, 100)
    assert route["selected_model"] == "model-b"
    for item in candidates:
        item["health"] = "UNAVAILABLE"
    with pytest.raises(RuntimeError, match="no fallback"):
        model.advanced.route_model("code", candidates, "INTERNAL", 0.2, 1, 100)


def test_metacognition_is_structured_and_does_not_modify_policy(tmp_path):
    model = dcml(tmp_path)
    before = model.status()["active_policy_checkpoint"]
    review = model.advanced.metacognitive_review(
        "cycle-1", 0.95, 0, [], ["unsupported claim"], 4, 0, 1, 0.4, False
    )
    assert review["human_review_required"] is True
    assert review["overconfidence"] is True
    assert review["context_loss"] is True
    assert review["learning_proposal_id"] is not None
    assert model.status()["active_policy_checkpoint"] == before


def test_long_horizon_mission_assigns_delayed_temporal_credit(tmp_path):
    model = dcml(tmp_path)
    mission = model.advanced.create_mission(
        "repair and verify",
        ["tests pass"],
        ["no production effects"],
        ["inspect", "repair", "verify"],
        ["repository"],
    )
    model.advanced.record_mission_stage(
        mission, 1, "inspect", "baseline", 0.5, ["inspection"]
    )
    model.advanced.record_mission_stage(
        mission, 2, "repair", "verified_procedure", 0.7, ["diff"]
    )
    model.advanced.record_mission_stage(
        mission, 3, "verify", "verified_procedure", 0.9, ["tests"]
    )
    credits = model.advanced.complete_mission(
        mission, "tests pass", 1.0, ["test-report"]
    )
    values = [
        model.advanced._get("temporal_credit", item)["payload"]["delayed_reward"]
        for item in credits
    ]
    assert len(values) == 3 and sum(values) == pytest.approx(1.0)
    assert values[-1] > values[0]


def test_versioned_skill_contains_governed_execution_contract(tmp_path):
    model = dcml(tmp_path)
    skill = model.advanced.create_skill(
        "verified-repair",
        "repair code with evidence",
        ["repository"],
        ["verified diff"],
        ["clean worktree"],
        ["inspect", "patch", "test"],
        ["git", "pytest"],
        ["healthy specialist"],
        ["passing test"],
        ["test failure"],
        ["experience-1"],
        "approval-1",
    )
    payload = model.advanced._get("skill_records", skill)["payload"]
    assert payload["version"] == 1 and payload["approval_state"] == "APPROVED"
    assert payload["rollback_state"] == "AVAILABLE"


def test_calibration_is_tracked_by_all_required_dimensions(tmp_path):
    model = dcml(tmp_path)
    result = model.advanced.calibrate_dimensions(
        [
            {
                "task_type": "code",
                "strategy": "verified",
                "model_id": "codex",
                "mission_class": "repair",
                "evidence_class": "passing_test",
                "predicted_confidence": 0.9,
                "observed_correctness": 1,
            },
            {
                "task_type": "code",
                "strategy": "verified",
                "model_id": "codex",
                "mission_class": "repair",
                "evidence_class": "passing_test",
                "predicted_confidence": 0.8,
                "observed_correctness": 0,
            },
        ]
    )
    assert result["dimensions"]["task_type"]["code"]["brier_score"] == pytest.approx(
        0.325
    )
    assert result["dimensions"]["model_id"]["codex"]["expected_calibration_error"] >= 0


def test_complete_benchmark_requires_all_categories_and_persists_result(tmp_path):
    model = dcml(tmp_path)
    categories = {
        "session_identity_continuity",
        "memory_retrieval",
        "belief_conflict_retention",
        "evidence_belief_revision",
        "prediction_accuracy",
        "uncertainty_calibration",
        "causal_reasoning",
        "counterfactual_comparison",
        "strategy_selection",
        "learning_approval_gating",
        "transfer_unseen_tasks",
        "model_routing",
        "failure_recovery",
        "checkpoint_rollback",
        "forgetting_resistance",
        "unsupported_claim_prevention",
        "telemetry_separation",
        "runtime_model_boundary",
    }
    with pytest.raises(ValueError, match="missing benchmark"):
        model.advanced.benchmark_suite({}, "baseline")
    result = model.advanced.benchmark_suite(
        {name: 1.0 for name in categories}, "post-learning"
    )
    assert result["task_success_rate"] == 1.0
    assert result["regression_count"] == 0

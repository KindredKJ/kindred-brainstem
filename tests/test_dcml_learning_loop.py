import json

import pytest

from brainstem.model.authority import FounderAuthority
from brainstem.model.dcml import DCMLLearning
from brainstem.runtime.store import StateStore


def manager(tmp_path):
    store = StateStore(tmp_path / "dcml.db", tmp_path / "events.jsonl")
    dcml = DCMLLearning(store)
    dcml.authority = FounderAuthority(store, tmp_path / "authority")
    dcml.authority.initialize()
    return dcml, store


def add_verified(dcml, index, strategy="verified_procedure", reward=1.0, private=False):
    exp = dcml.record_experience(
        session_id="session",
        mission_id="mission-training",
        goal="repair verified code",
        input_state={"task": f"code repository verify test case {index}"},
        selected_strategy=strategy,
        selected_instrument="SIMULATED_SPECIALIST",
        context_supplied={"case": index},
        predicted_outcome="passing_test",
        success_criteria={"expected_outcome": "passing_test"},
        confidence=0.4,
        privacy_classification="RESTRICTED" if private else "INTERNAL_APPROVED",
        retention_classification="LEARNING_APPROVED",
        provenance=[f"case-{index}"],
    )
    dcml.observe(exp, "passing_test", reward, cost=0.1, latency_ms=10)
    dcml.verify_experience(
        exp, "passing_test", {"test": f"SIMULATED-{index}", "passed": True}
    )
    evaluation = dcml.evaluate(exp)
    credit = dcml.assign_credit(exp, evaluation)
    content_hash = dcml._get("experiences_v2", exp)["content_hash"]
    approval = dcml.authority.sign(f"learn:{exp}", "experience-learning", content_hash)
    dcml.approve_for_learning(exp, approval)
    return exp, evaluation, credit, approval


def test_complete_policy_learning_improves_heldout_persists_and_rolls_back(tmp_path):
    dcml, store = manager(tmp_path)
    records = [add_verified(dcml, i) for i in range(8)]
    cases = [
        {
            "input_state": {"task": f"unseen code repository verify {i}"},
            "best_strategy": "verified_procedure",
        }
        for i in range(4)
    ]
    baseline = dcml.benchmark(cases, phase="pre-learning")
    assert baseline["task_success_rate"] == 0.0
    dataset_id = dcml.build_dataset(seed=17)
    dataset = dcml._get("datasets", dataset_id)["payload"]
    assert set(dataset["split"]["train"]).isdisjoint(dataset["split"]["test"])
    run_id, checkpoint_id = dcml.train(
        dataset_id, learning_rate=0.3, epochs=30, seed=17
    )
    training = dcml._get("training_runs", run_id)["payload"]
    assert (
        training["pre_training_metrics"]["parameter_hash"]
        != training["post_training_metrics"]["parameter_hash"]
    )
    assert (
        dcml.select_strategy(cases[0]["input_state"]) == "baseline"
    )  # candidate inactive
    canary_id = dcml.canary(checkpoint_id, cases, baseline["task_success_rate"])
    assert dcml._get("canary_results", canary_id)["payload"]["passed"] is True
    promotion = dcml.authority.sign(
        f"promote:{checkpoint_id}",
        "policy-promotion",
        dcml._get("policy_parameters", checkpoint_id)["content_hash"],
    )
    dcml.promote(checkpoint_id, canary_id, promotion)
    post = dcml.benchmark(cases, phase="post-learning")
    assert post["task_success_rate"] > baseline["task_success_rate"]
    assert dcml.select_strategy(cases[0]["input_state"]) == "verified_procedure"
    reopened = DCMLLearning(StateStore(store.path, tmp_path / "events.jsonl"))
    assert reopened.select_strategy(cases[0]["input_state"]) == "verified_procedure"
    reopened.authority = FounderAuthority(reopened.store, tmp_path / "authority")
    rollback = reopened.authority.sign(
        "rollback:KPOLICY-BASELINE",
        "policy-rollback",
        reopened._get("policy_parameters", "KPOLICY-BASELINE")["content_hash"],
    )
    reopened.rollback_policy("KPOLICY-BASELINE", rollback)
    assert reopened.select_strategy(cases[0]["input_state"]) == "baseline"
    assert len(records) == 8


def test_unverified_unapproved_private_and_secret_excluded(tmp_path):
    dcml, _ = manager(tmp_path)
    unverified = dcml.record_experience(
        session_id="s",
        goal="x",
        input_state={"text": "x"},
        selected_strategy="baseline",
        selected_instrument="SIMULATED",
        predicted_outcome="x",
        success_criteria={"expected_outcome": "x"},
        privacy_classification="INTERNAL_APPROVED",
        retention_classification="SHORT",
        provenance=["test"],
    )
    with pytest.raises(PermissionError):
        dcml.evaluate(unverified)
    approved, *_ = add_verified(dcml, 1)
    private, *_ = add_verified(dcml, 2, private=True)
    secret, *_ = add_verified(dcml, 3)
    row = dcml._get("experiences_v2", secret)
    data = row["payload"]
    data["input_state"] = {"api_key": "api_key=DO_NOT_TRAIN"}
    dcml.store.execute(
        "UPDATE experiences_v2 SET payload=?,content_hash=? WHERE id=?",
        (json.dumps(data, sort_keys=True), "changed", secret),
    )
    dataset = dcml._get("datasets", dcml.build_dataset())["payload"]
    assert approved in dataset["source_experience_ids"]
    assert private not in dataset["source_experience_ids"]
    assert secret not in dataset["source_experience_ids"]
    assert unverified not in dataset["source_experience_ids"]


def test_dataset_split_reproducible_and_approval_tamper_fails(tmp_path):
    dcml, store = manager(tmp_path)
    for i in range(6):
        add_verified(dcml, i)
    one = dcml._get("datasets", dcml.build_dataset(seed=99))["payload"]
    two = dcml._get("datasets", dcml.build_dataset(seed=99))["payload"]
    assert one["split"] == two["split"]
    exp = one["source_experience_ids"][0]
    approval = dcml.authority.sign(f"learn:{exp}", "test", dcml._get("experiences_v2", exp)["content_hash"])
    assert dcml.authority.verify(approval, f"learn:{exp}")
    record = store.query(
        "SELECT payload FROM signed_approvals WHERE id=?", (approval,)
    )[0]
    tampered = json.loads(record["payload"])
    tampered["payload"]["scope"] = "tampered"
    store.execute(
        "UPDATE signed_approvals SET payload=? WHERE id=?",
        (json.dumps(tampered), approval),
    )
    assert not dcml.authority.verify(approval, f"learn:{exp}")


def test_generated_and_simulated_evidence_never_verify_external_result(tmp_path):
    dcml, _ = manager(tmp_path)
    exp = dcml.record_experience(
        session_id="s",
        goal="deploy",
        input_state={},
        selected_strategy="baseline",
        selected_instrument="SIMULATED",
        predicted_outcome="deployed",
        success_criteria={"expected_outcome": "deployed"},
        privacy_classification="PUBLIC",
        retention_classification="SHORT",
        provenance=["test"],
    )
    for kind in ("generated_output", "simulated_outcome", "local_artifact"):
        verification = dcml.verify_experience(exp, kind, {"claim": "deployed"})
        assert dcml._get("verifications", verification)["status"] == "UNVERIFIED"
    assert dcml._get("experiences_v2", exp)["status"] == "UNVERIFIED"


def test_regressive_canary_blocks_promotion(tmp_path):
    dcml, _ = manager(tmp_path)
    add_verified(dcml, 1)
    dataset = dcml.build_dataset()
    _, checkpoint = dcml.train(dataset)
    cases = [
        {"input_state": {"task": "code repository verify"}, "best_strategy": "baseline"}
    ]
    canary = dcml.canary(checkpoint, cases, baseline=1.0)
    assert dcml._get("canary_results", canary)["status"] == "BLOCKED"
    approval = dcml.authority.sign(
        f"promote:{checkpoint}",
        "test",
        dcml._get("policy_parameters", checkpoint)["content_hash"],
    )
    with pytest.raises(PermissionError, match="Canary failed"):
        dcml.promote(checkpoint, canary, approval)

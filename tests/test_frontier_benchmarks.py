import json

import pytest
from pydantic import ValidationError

from brainstem.benchmarks.contamination import ContaminationScanner
from brainstem.benchmarks.contracts import Configuration, SystemManifest
from brainstem.benchmarks.registry import BenchmarkRegistry, SUITES
from brainstem.benchmarks.runner import FrontierRunner
from brainstem.benchmarks.seal import BenchmarkSeal
from brainstem.runtime.store import StateStore


def test_registry_is_external_complete_and_conservative(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("KINDRED_BENCHMARK_") and key.endswith("_CMD"):
            monkeypatch.delenv(key, raising=False)
    registry = BenchmarkRegistry()
    rows = registry.list()
    assert len(rows) == 12
    assert all(row["category"] == "EXTERNAL_FRONTIER_BENCHMARK" for row in rows)
    assert all(
        row["status"]
        in {
            "NOT_CONFIGURED",
            "LICENSE_REQUIRED",
            "DATASET_REQUIRED",
            "ENVIRONMENT_REQUIRED",
            "BLOCKED",
            "AVAILABLE",
            "VERIFIED",
        }
        for row in rows
    )
    assert set(SUITES) == {"frontier-core", "frontier-agentic", "frontier-full"}


def test_honest_system_name_rejects_missing_provider_attribution():
    base = dict(
        configuration=Configuration.ATTACHED_MODEL_DIRECT,
        brainstem_commit="a",
        runtime_commit="a",
        attached_provider="Codex",
        model_identifier="gpt",
        adapter_version="1",
        benchmark_version="1",
        dataset_hash="d",
        prompt_template_hash="p",
        tool_configuration={},
        inference_setting="default",
        seed=1,
        token_budget=1,
        time_budget_seconds=1,
        cost_budget=0,
        retry_budget=0,
        hardware="x",
        operating_system="x",
    )
    with pytest.raises(ValidationError, match="attached provider"):
        SystemManifest(system_name="BRAINSTEM", **base)
    assert (
        SystemManifest(system_name="Codex direct + gpt", **base).attached_provider
        == "Codex"
    )


def test_seal_blocks_canonical_writes_but_not_unrelated_state(tmp_path):
    seal = BenchmarkSeal(tmp_path / "state")
    seal.seal()
    from brainstem.benchmarks import seal as seal_module

    original = seal_module.BenchmarkSeal
    seal_module.BenchmarkSeal = lambda: seal
    try:
        store = StateStore(tmp_path / "state.db")
        with pytest.raises(PermissionError, match="canonical cognitive writes"):
            store.execute(
                "INSERT INTO memory VALUES (?,?,?,?,?,?,?,?)",
                ("x", "x", "x", "x", "x", 1, "x", "x"),
            )
        with pytest.raises(PermissionError, match="canonical cognitive writes"):
            store.add_message("benchmark-session", "user", "sealed test question")
        with pytest.raises(PermissionError, match="canonical cognitive writes"):
            store.add_evidence("benchmark-session", "answer_key", {"answer": "x"})
        store.execute(
            "INSERT INTO events VALUES (?,?,?,?)",
            ("id", "benchmark.unrelated", "{}", "now"),
        )
    finally:
        seal_module.BenchmarkSeal = original
        seal.unseal()


def test_contamination_scanner_hashes_findings_and_never_claims_clean(tmp_path):
    (tmp_path / "artifact.txt").write_text("distinctive benchmark canary 123456")
    report = ContaminationScanner().scan(
        [tmp_path], {"benchmark_canary": ["benchmark canary 123456"]}
    )
    assert report["status"] == "CONTAMINATED"
    assert report["officially_clean"] is False
    assert "signature_hash" in report["findings"][0]


def test_runner_fails_closed_when_unsealed_or_not_configured(tmp_path):
    seal = BenchmarkSeal(tmp_path / "state")
    runner = FrontierRunner(tmp_path / "runs", seal)
    with pytest.raises(PermissionError, match="sealed mode"):
        runner.run("mmlu-pro", Configuration.ATTACHED_MODEL_DIRECT, "Codex", "gpt")
    seal.seal()
    result = runner.run(
        "mmlu-pro", Configuration.ATTACHED_MODEL_DIRECT, "Codex", "gpt", signatures={}
    )
    assert result["status"] == "NOT_CONFIGURED"


def test_configured_test_evaluator_generates_all_reproducibility_artifacts(
    tmp_path, monkeypatch
):
    evaluator = tmp_path / "test_evaluator.py"
    evaluator.write_text("import json\nprint(json.dumps({'accuracy': 0.5}))\n")
    monkeypatch.setenv("KINDRED_BENCHMARK_MMLU_PRO_CMD", f"python {evaluator}")
    seal = BenchmarkSeal(tmp_path / "state")
    seal.seal()
    runner = FrontierRunner(tmp_path / "runs", seal)
    result = runner.run(
        "mmlu-pro",
        Configuration.ATTACHED_MODEL_DIRECT,
        "TEST_ONLY_PROVIDER",
        "TEST_ONLY_MODEL",
        repetitions=2,
        seeds=[7, 8],
        signatures={"benchmark_canary": ["absent-" + "canary-12345678"]},
    )
    assert result["status"] == "COMPLETED"
    assert result["official_score"] is False
    assert result["tool_policy"] == "NONSTANDARD"
    assert result["repetitions"]["mean"] == 0.5
    run_dir = tmp_path / "runs" / result["run_id"]
    assert {p.name for p in run_dir.iterdir()} == {
        "manifest.json",
        "results.json",
        "contamination.json",
        "attribution.json",
        "report.md",
    }
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["system_name"] == "TEST_ONLY_PROVIDER direct + TEST_ONLY_MODEL"
    assert (
        json.loads((run_dir / "attribution.json").read_text())["status"]
        == "ASSOCIATIONAL_NOT_CAUSAL"
    )


def test_contaminated_run_is_excluded(tmp_path, monkeypatch):
    evaluator = tmp_path / "evaluator.py"
    evaluator.write_text("print('never reached')\n")
    marker = tmp_path / "marker.txt"
    marker.write_text("secret benchmark answer marker 123456")
    monkeypatch.setenv("KINDRED_BENCHMARK_MMLU_PRO_CMD", f"python {evaluator}")
    seal = BenchmarkSeal(tmp_path / "state")
    seal.seal()
    runner = FrontierRunner(tmp_path / "runs", seal)
    # Scanner intentionally scans cwd; point cwd to controlled fixture.
    monkeypatch.chdir(tmp_path)
    result = runner.run(
        "mmlu-pro",
        Configuration.ATTACHED_MODEL_DIRECT,
        "TEST_ONLY",
        "TEST_ONLY",
        signatures={"answer_key": ["benchmark answer marker 123456"]},
    )
    assert result["status"] == "CONTAMINATED"
    assert result["official_score"] is False


def test_publication_gate_requires_every_control(tmp_path):
    runner = FrontierRunner(tmp_path)
    denied = runner.publication_gate("r", {"license_compliance": True})
    assert (
        denied["status"] == "INTERNAL_ONLY" and "founder_approval" in denied["missing"]
    )
    keys = [
        "license_compliance",
        "clean_contamination",
        "complete_manifest",
        "reproducible_command",
        "frozen_commit",
        "frozen_checkpoint",
        "evaluator_integrity",
        "no_hidden_test_access",
        "no_test_learning",
        "successful_rerun",
        "founder_approval",
    ]
    assert (
        runner.publication_gate("r", {key: True for key in keys})["status"]
        == "APPROVED_FOR_PUBLICATION"
    )


def test_post_learning_and_rollback_require_frozen_checkpoint(tmp_path, monkeypatch):
    evaluator = tmp_path / "evaluator.py"
    evaluator.write_text("import json\nprint(json.dumps({'accuracy': 1}))\n")
    monkeypatch.setenv("KINDRED_BENCHMARK_MMLU_PRO_CMD", f"python {evaluator}")
    seal = BenchmarkSeal(tmp_path / "state")
    seal.seal()
    runner = FrontierRunner(tmp_path / "runs", seal)
    with pytest.raises(ValueError, match="frozen checkpoint"):
        runner.run(
            "mmlu-pro",
            Configuration.BRAINSTEM_DCML_POST_LEARNING,
            "TEST_ONLY",
            "TEST_ONLY",
            signatures={},
        )
    with pytest.raises(PermissionError, match="forbidden"):
        runner.run(
            "mmlu-pro",
            Configuration.ATTACHED_MODEL_DIRECT,
            "TEST_ONLY",
            "TEST_ONLY",
            signatures={},
            partition="hidden",
        )

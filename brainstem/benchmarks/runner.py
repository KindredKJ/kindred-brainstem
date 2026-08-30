"""Isolated external runner, reports, repeated statistics, comparison and publication gate."""

from __future__ import annotations
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any
from .adapters import adapter_for
from .contamination import ContaminationScanner
from .contracts import (
    Configuration,
    Metrics,
    PublicationStatus,
    RepeatedStatistics,
    SystemManifest,
    ToolPolicy,
)
from .registry import BenchmarkRegistry
from .seal import BenchmarkSeal


def canonical(v: Any) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


def sha(v: Any) -> str:
    return hashlib.sha256(canonical(v).encode()).hexdigest()


def git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


class FrontierRunner:
    def __init__(
        self,
        output_root: Path = Path("generated/benchmarks"),
        seal: BenchmarkSeal | None = None,
    ):
        self.output_root = output_root
        self.seal = seal or BenchmarkSeal()
        self.registry = BenchmarkRegistry()

    def _system_name(
        self, configuration: Configuration, provider: str | None, model: str | None
    ) -> str:
        if configuration == Configuration.BRAINSTEM_NATIVE_ONLY:
            return "BRAINSTEM native policy model only"
        if provider:
            return (
                f"BRAINSTEM-DCML + {provider} + {model or 'model identifier unavailable'}"
                if configuration != Configuration.ATTACHED_MODEL_DIRECT
                else f"{provider} direct + {model or 'model identifier unavailable'}"
            )
        raise ValueError(
            "attached provider is required outside native-only configuration"
        )

    def run(
        self,
        slug: str,
        configuration: Configuration,
        provider: str | None = None,
        model: str | None = None,
        repetitions: int = 1,
        seeds: list[int] | None = None,
        signatures: dict[str, list[str]] | None = None,
        signature_sources: list[Path] | None = None,
        partition: str = "held_out",
        checkpoint: str | None = None,
    ) -> dict:
        self.seal.require()
        spec = self.registry.get(slug)
        if partition in {"hidden", "private_test", "answer_keys"}:
            raise PermissionError(
                "hidden, private-test, and answer-key partitions are forbidden"
            )
        if partition not in spec.partitions:
            raise ValueError(f"unknown benchmark partition alias: {partition}")
        resolved_partition = spec.partitions[partition]
        if (
            configuration
            in {
                Configuration.BRAINSTEM_DCML_POST_LEARNING,
                Configuration.BRAINSTEM_DCML_ROLLBACK,
            }
            and not checkpoint
        ):
            raise ValueError(f"{configuration.value} requires a frozen checkpoint")
        if configuration == Configuration.BRAINSTEM_NATIVE_ONLY and spec.domain not in {
            "abstract_generalization"
        }:
            return {
                "benchmark": slug,
                "configuration": configuration.value,
                "status": "NOT_CONFIGURED",
                "reason": "native BRAINSTEM lacks this task executor",
            }
        doctor = adapter_for(spec).doctor()
        if doctor["status"] != "AVAILABLE":
            return {**doctor, "configuration": configuration.value}
        if signatures is None:
            return {
                "benchmark": slug,
                "configuration": configuration.value,
                "status": "BLOCKED",
                "reason": "a benchmark-maintainer-derived contamination signature manifest is required",
            }
        run_id = f"KBENCH-{uuid.uuid4().hex[:12].upper()}"
        run_dir = self.output_root / run_id
        run_dir.mkdir(parents=True)
        seeds = seeds or list(range(repetitions))
        values = []
        raw = []
        failures: dict[str, int] = {}
        with tempfile.TemporaryDirectory(prefix="kindred-benchmark-") as td:
            workspace_root = Path(td)
            os.chmod(workspace_root, 0o700)
            contamination = ContaminationScanner().scan(
                [Path.cwd()], signatures, signature_sources or []
            )
            if contamination["status"] == "CONTAMINATED":
                return self._write_contaminated(
                    run_dir, run_id, spec, configuration, contamination
                )
            for seed in seeds[:repetitions]:
                try:
                    workspace = workspace_root / f"seed-{seed}-{len(raw)}"
                    workspace.mkdir(mode=0o700)
                    item = adapter_for(spec).execute(
                        workspace, configuration.value, seed, resolved_partition, checkpoint
                    )
                    raw.append(item)
                    metric_name = spec.official_metrics[0]
                    aliases = {"pass@1": ("pass@1", "pass_at_1")}.get(metric_name, (metric_name,))
                    present = next((name for name in aliases if name in item), None)
                    if present is None or isinstance(item[present], bool):
                        raise ValueError(f"evaluator omitted official metric {metric_name}")
                    value = float(item[present])
                    if not math.isfinite(value):
                        raise ValueError(f"evaluator returned invalid metric {metric_name}")
                    values.append(value)
                except Exception as exc:
                    kind = type(exc).__name__
                    failures[kind] = failures.get(kind, 0) + 1
        mean = statistics.mean(values) if values else 0.0
        sd = statistics.stdev(values) if len(values) > 1 else 0.0
        margin = 1.96 * sd / math.sqrt(len(values)) if values else 0
        stats = RepeatedStatistics(
            count=len(values),
            mean=mean,
            median=statistics.median(values) if values else 0,
            standard_deviation=sd,
            confidence_interval_95=(mean - margin, mean + margin),
            best=max(values, default=0),
            worst=min(values, default=0),
            failures=failures,
        )
        metric = Metrics(
            accuracy=mean if "accuracy" in spec.official_metrics else None,
            pass_at_1=mean if "pass@1" in spec.official_metrics else None,
            task_success_rate=mean
            if "task_success_rate" in spec.official_metrics
            else None,
            partial_credit_score=(
                statistics.mean(
                    float(item["partial_credit_score"])
                    for item in raw
                    if "partial_credit_score" in item
                )
                if any("partial_credit_score" in item for item in raw)
                else None
            ),
            wall_clock_seconds=sum(
                float(item.get("_harness_wall_clock_seconds", 0)) for item in raw
            ),
            token_usage=sum(int(item.get("token_usage", 0)) for item in raw),
            model_calls=sum(int(item.get("model_calls", 0)) for item in raw),
            tool_calls=sum(int(item.get("tool_calls", 0)) for item in raw),
            retries=sum(int(item.get("retries", 0)) for item in raw),
            estimated_cost=sum(float(item.get("estimated_cost", 0)) for item in raw),
            failures=sum(failures.values()),
            timeouts=failures.get("TimeoutExpired", 0),
        )
        commit = git_head()
        manifest = SystemManifest(
            system_name=self._system_name(configuration, provider, model),
            configuration=configuration,
            brainstem_commit=commit,
            runtime_commit=commit,
            dcml_checkpoint=checkpoint,
            attached_provider=provider,
            model_identifier=model,
            adapter_version="1",
            benchmark_version=spec.version,
            dataset_hash=os.getenv("KINDRED_BENCHMARK_DATASET_HASH", "UNVERIFIED"),
            prompt_template_hash=os.getenv(
                "KINDRED_BENCHMARK_PROMPT_HASH", "UNVERIFIED"
            ),
            tool_configuration=spec.tool_policy,
            inference_setting=os.getenv(
                "KINDRED_BENCHMARK_INFERENCE_SETTING", "provider-default"
            ),
            seed=seeds[0],
            token_budget=int(os.getenv("KINDRED_BENCHMARK_TOKEN_BUDGET", "0")),
            time_budget_seconds=3600,
            cost_budget=float(os.getenv("KINDRED_BENCHMARK_COST_BUDGET", "0")),
            retry_budget=0,
            hardware=platform.machine(),
            operating_system=platform.platform(),
        )
        result = {
            "run_id": run_id,
            "benchmark": slug,
            "category": "EXTERNAL_FRONTIER_BENCHMARK",
            "configuration": configuration.value,
            "status": "COMPLETED" if len(values) == repetitions else "FAILED",
            "tool_policy": (
                ToolPolicy.STANDARD.value
                if os.getenv("KINDRED_BENCHMARK_TOOL_POLICY_VERIFIED") == "1"
                else ToolPolicy.NONSTANDARD.value
            ),
            "official_score": bool(
                len(values) == repetitions
                and os.getenv("KINDRED_BENCHMARK_TOOL_POLICY_VERIFIED") == "1"
                and os.getenv("KINDRED_BENCHMARK_EVALUATOR_VERIFIED") == "1"
                and manifest.dataset_hash != "UNVERIFIED"
            ),
            "metrics": metric.model_dump(),
            "repetitions": stats.model_dump(),
            "contamination_status": contamination["status"],
            "limitations": [contamination["remaining_risk"]],
            "raw_result_hash": sha(raw),
        }
        attribution = {
            "status": "ASSOCIATIONAL_NOT_CAUSAL",
            "requires_ablations": True,
            "components": [
                "attached_model",
                "context_assembly",
                "retrieval",
                "strategy_selection",
                "counterfactual_simulation",
                "tool_routing",
                "reflection",
                "retry_policy",
                "learned_policy_parameters",
                "persistent_memory",
                "outcome_verification",
            ],
        }
        self._write(
            run_dir,
            manifest.model_dump(mode="json"),
            result,
            contamination,
            attribution,
        )
        return result

    def _write_contaminated(self, run_dir, run_id, spec, configuration, contamination):
        result = {
            "run_id": run_id,
            "benchmark": spec.slug,
            "configuration": configuration.value,
            "status": "CONTAMINATED",
            "official_score": False,
        }
        self._write(run_dir, {}, result, contamination, {"status": "EXCLUDED"})
        return result

    def _write(
        self,
        d: Path,
        manifest: dict,
        result: dict,
        contamination: dict,
        attribution: dict,
    ):
        for name, data in (
            ("manifest", manifest),
            ("results", result),
            ("contamination", contamination),
            ("attribution", attribution),
        ):
            (d / f"{name}.json").write_text(
                json.dumps(data, indent=2, sort_keys=True) + "\n"
            )
        (d / "report.md").write_text(
            f"# External benchmark {result.get('run_id')}\n\n- Status: `{result.get('status')}`\n- Benchmark: `{result.get('benchmark')}`\n- Configuration: `{result.get('configuration')}`\n- Official score: `{result.get('official_score', False)}`\n- Contamination: `{result.get('contamination_status', 'CONTAMINATED')}`\n- Publication: `INTERNAL_ONLY`\n\nThis report does not claim causation, frontier performance, or independent verification.\n"
        )

    def report(self, run_id: str) -> dict:
        return json.loads((self.output_root / run_id / "results.json").read_text())

    def compare(self, a: str, b: str) -> dict:
        ra, rb = self.report(a), self.report(b)
        ma = ra.get("repetitions", {}).get("mean")
        rbm = rb.get("repetitions", {}).get("mean")
        return {
            "run_a": a,
            "run_b": b,
            "delta": None if ma is None or rbm is None else rbm - ma,
            "causal_claim": False,
        }

    def publication_gate(self, run_id: str, checks: dict[str, bool]) -> dict:
        required = (
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
        )
        eligible = all(checks.get(k, False) for k in required)
        return {
            "run_id": run_id,
            "status": PublicationStatus.APPROVED_FOR_PUBLICATION.value
            if eligible
            else PublicationStatus.INTERNAL_ONLY.value,
            "missing": [k for k in required if not checks.get(k, False)],
        }

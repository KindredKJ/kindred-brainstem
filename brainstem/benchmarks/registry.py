"""Conservative registry of official frontier suites; registration is not readiness."""

from __future__ import annotations
import os
from typing import Any, cast
from .contracts import AdapterStatus, BenchmarkSpec

_DATA = [
    (
        "MMLU-Pro",
        "mmlu-pro",
        "reasoning",
        "official-current",
        "https://github.com/TIGER-AI-Lab/MMLU-Pro",
        "MIT; dataset terms must be reviewed",
        ["dataset"],
        ["accuracy"],
        {"browsing": False},
        {"held_out": "test"},
        "KINDRED_BENCHMARK_MMLU_PRO_CMD",
    ),
    (
        "GPQA Diamond",
        "gpqa-diamond",
        "reasoning",
        "official-current",
        "https://github.com/idavidrein/gpqa",
        "dataset access terms apply",
        ["dataset"],
        ["accuracy"],
        {"browsing": False},
        {"development": "train", "held_out": "diamond"},
        "KINDRED_BENCHMARK_GPQA_CMD",
    ),
    (
        "LiveBench",
        "livebench",
        "reasoning",
        "official-current",
        "https://github.com/LiveBench/LiveBench",
        "official repository terms",
        ["dataset", "evaluator"],
        ["accuracy"],
        {"browsing": False},
        {"held_out": "official"},
        "KINDRED_BENCHMARK_LIVEBENCH_CMD",
    ),
    (
        "ARC-AGI-2",
        "arc-agi-2",
        "abstract_generalization",
        "official-current",
        "https://github.com/arcprize/ARC-AGI-2",
        "Apache-2.0 repository; competition terms may apply",
        ["dataset", "evaluator"],
        ["accuracy"],
        {"browsing": False},
        {"development": "training", "held_out": "evaluation"},
        "KINDRED_BENCHMARK_ARC_AGI_2_CMD",
    ),
    (
        "Berkeley Function Calling Leaderboard",
        "bfcl",
        "tool_use",
        "stable-current",
        "https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard",
        "Apache-2.0 repository",
        ["dataset", "evaluator"],
        ["accuracy"],
        {"functions": "official-only"},
        {"held_out": "official"},
        "KINDRED_BENCHMARK_BFCL_CMD",
    ),
    (
        "GAIA",
        "gaia",
        "agentic",
        "official-current",
        "https://huggingface.co/gaia-benchmark",
        "dataset access approval required",
        ["dataset", "browsing_environment"],
        ["task_success_rate"],
        {"browsing": True},
        {"development": "validation", "held_out": "test"},
        "KINDRED_BENCHMARK_GAIA_CMD",
    ),
    (
        "GAIA2",
        "gaia2",
        "agentic",
        "official-current",
        "https://github.com/gaia-benchmark",
        "official environment not established locally",
        ["official_environment"],
        ["task_success_rate"],
        {"official_environment": True},
        {"held_out": "official"},
        "KINDRED_BENCHMARK_GAIA2_CMD",
    ),
    (
        "BrowseComp",
        "browsecomp",
        "agentic",
        "official-current",
        "https://github.com/openai/simple-evals",
        "official repository terms",
        ["dataset", "live_web"],
        ["accuracy"],
        {"browsing": True},
        {"held_out": "official"},
        "KINDRED_BENCHMARK_BROWSECOMP_CMD",
    ),
    (
        "SWE-bench Verified",
        "swe-bench-verified",
        "coding",
        "official-current",
        "https://github.com/SWE-bench/SWE-bench",
        "MIT; instance repositories retain their licenses",
        ["dataset", "docker"],
        ["pass@1"],
        {"official_container": True},
        {"held_out": "verified"},
        "KINDRED_BENCHMARK_SWEBENCH_CMD",
    ),
    (
        "SWE-Lancer Diamond",
        "swe-lancer-diamond",
        "coding",
        "official-current",
        "https://github.com/openai/swelancer-benchmark",
        "official dataset access terms",
        ["dataset", "docker"],
        ["task_success_rate"],
        {"official_container": True},
        {"held_out": "diamond"},
        "KINDRED_BENCHMARK_SWELANCER_CMD",
    ),
    (
        "LiveCodeBench",
        "livecodebench",
        "coding",
        "official-current",
        "https://github.com/LiveCodeBench/LiveCodeBench",
        "official repository and dataset terms",
        ["dataset", "evaluator"],
        ["pass@1"],
        {"browsing": False},
        {"held_out": "official"},
        "KINDRED_BENCHMARK_LIVECODEBENCH_CMD",
    ),
    (
        "OSWorld 2.0",
        "osworld-2",
        "computer_use",
        "2.0",
        "https://github.com/xlang-ai/OSWorld",
        "official gated task package and VM required",
        ["gated_tasks", "virtual_machine"],
        ["task_success_rate"],
        {"official_vm": True},
        {"held_out": "official"},
        "KINDRED_BENCHMARK_OSWORLD2_CMD",
    ),
]


class BenchmarkRegistry:
    def __init__(self) -> None:
        self._specs = {
            x[1]: BenchmarkSpec(
                name=x[0],
                slug=x[1],
                domain=x[2],
                version=x[3],
                official_url=x[4],
                license=x[5],
                access_notes=x[5],
                required_environment=x[6],
                official_metrics=x[7],
                tool_policy=cast(dict[str, Any], x[8]),
                partitions=cast(dict[str, str], x[9]),
                default_status=AdapterStatus.NOT_CONFIGURED,
                command_env=x[10],
            )
            for x in _DATA
        }

    def list(self) -> list[dict]:
        return [
            {**s.model_dump(mode="json"), "status": self.status(s).value}
            for s in self._specs.values()
        ]

    def get(self, slug: str) -> BenchmarkSpec:
        if slug not in self._specs:
            raise KeyError(slug)
        return self._specs[slug]

    def status(self, spec: BenchmarkSpec) -> AdapterStatus:
        if os.getenv(spec.command_env):
            return AdapterStatus.AVAILABLE
        if "gated" in " ".join(spec.required_environment) or spec.slug in {
            "gaia",
            "gaia2",
            "osworld-2",
        }:
            return AdapterStatus.LICENSE_REQUIRED
        if spec.required_environment:
            return AdapterStatus.DATASET_REQUIRED
        return spec.default_status


SUITES = {
    "frontier-core": ["arc-agi-2", "gpqa-diamond", "mmlu-pro", "livebench"],
    "frontier-agentic": ["gaia", "browsecomp", "bfcl", "swe-bench-verified"],
}
SUITES["frontier-full"] = [
    *SUITES["frontier-core"],
    *SUITES["frontier-agentic"],
    "swe-lancer-diamond",
    "livecodebench",
    "osworld-2",
    "gaia2",
]

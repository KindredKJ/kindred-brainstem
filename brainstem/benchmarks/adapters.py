"""Fail-closed adapters for official benchmark commands configured by operators."""

from __future__ import annotations
import json
import os
import shlex
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from .contracts import AdapterStatus, BenchmarkSpec


class BenchmarkAdapter(ABC):
    def __init__(self, spec: BenchmarkSpec):
        self.spec = spec

    @abstractmethod
    def doctor(self) -> dict: ...
    @abstractmethod
    def execute(
        self,
        workspace: Path,
        configuration: str,
        seed: int,
        partition: str,
        checkpoint: str | None,
    ) -> dict: ...


class OfficialCommandAdapter(BenchmarkAdapter):
    """Invokes only an explicitly configured official evaluator; never downloads data."""

    def doctor(self) -> dict:
        command = os.getenv(self.spec.command_env)
        return {
            "benchmark": self.spec.slug,
            "status": AdapterStatus.AVAILABLE.value
            if command
            else AdapterStatus.NOT_CONFIGURED.value,
            "command_configured": bool(command),
            "required_environment": self.spec.required_environment,
            "automatic_download": False,
        }

    def execute(
        self,
        workspace: Path,
        configuration: str,
        seed: int,
        partition: str,
        checkpoint: str | None,
    ) -> dict:
        command = os.getenv(self.spec.command_env)
        if not command:
            raise RuntimeError(f"{self.spec.command_env} is not configured")
        allowed = {"PATH", "HOME", "TMPDIR", "SYSTEMROOT", "COMSPEC"}
        allowed.update(
            name.strip()
            for name in os.getenv("KINDRED_BENCHMARK_PASSTHROUGH", "").split(",")
            if name.strip()
        )
        env = {
            **{name: os.environ[name] for name in allowed if name in os.environ},
            "KINDRED_BENCHMARK_WORKSPACE": str(workspace),
            "KINDRED_BENCHMARK_CONFIGURATION": configuration,
            "KINDRED_BENCHMARK_SEED": str(seed),
            "KINDRED_BENCHMARK_PARTITION": partition,
            "KINDRED_BENCHMARK_LEARNING_FROZEN": "1",
        }
        if checkpoint:
            env["KINDRED_BENCHMARK_CHECKPOINT"] = checkpoint
        started = time.monotonic()
        result = subprocess.run(
            shlex.split(command),
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                f"official evaluator failed ({result.returncode}): {result.stderr[-500:]}"
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("official evaluator must emit one JSON result") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("official evaluator JSON result must be an object")
        payload["_harness_wall_clock_seconds"] = time.monotonic() - started
        return payload


class MMLUProAdapter(OfficialCommandAdapter):
    pass


class GPQADiamondAdapter(OfficialCommandAdapter):
    pass


class LiveBenchAdapter(OfficialCommandAdapter):
    pass


class ARCAGI2Adapter(OfficialCommandAdapter):
    pass


class BFCLAdapter(OfficialCommandAdapter):
    pass


class GAIAAdapter(OfficialCommandAdapter):
    pass


class GAIA2Adapter(OfficialCommandAdapter):
    pass


class BrowseCompAdapter(OfficialCommandAdapter):
    pass


class SWEBenchVerifiedAdapter(OfficialCommandAdapter):
    pass


class SWELancerDiamondAdapter(OfficialCommandAdapter):
    pass


class LiveCodeBenchAdapter(OfficialCommandAdapter):
    pass


class OSWorld2Adapter(OfficialCommandAdapter):
    pass


ADAPTER_TYPES = {
    "mmlu-pro": MMLUProAdapter,
    "gpqa-diamond": GPQADiamondAdapter,
    "livebench": LiveBenchAdapter,
    "arc-agi-2": ARCAGI2Adapter,
    "bfcl": BFCLAdapter,
    "gaia": GAIAAdapter,
    "gaia2": GAIA2Adapter,
    "browsecomp": BrowseCompAdapter,
    "swe-bench-verified": SWEBenchVerifiedAdapter,
    "swe-lancer-diamond": SWELancerDiamondAdapter,
    "livecodebench": LiveCodeBenchAdapter,
    "osworld-2": OSWorld2Adapter,
}


def adapter_for(spec: BenchmarkSpec) -> OfficialCommandAdapter:
    return ADAPTER_TYPES[spec.slug](spec)

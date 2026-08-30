"""Typed contracts for external frontier evaluation; never internal DCML scores."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field, model_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvaluationCategory(StrEnum):
    INTERNAL_DCML_EVALUATION = "INTERNAL_DCML_EVALUATION"
    EXTERNAL_FRONTIER_BENCHMARK = "EXTERNAL_FRONTIER_BENCHMARK"


class AdapterStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    LICENSE_REQUIRED = "LICENSE_REQUIRED"
    DATASET_REQUIRED = "DATASET_REQUIRED"
    ENVIRONMENT_REQUIRED = "ENVIRONMENT_REQUIRED"
    BLOCKED = "BLOCKED"
    VERIFIED = "VERIFIED"


class Configuration(StrEnum):
    ATTACHED_MODEL_DIRECT = "ATTACHED_MODEL_DIRECT"
    BRAINSTEM_STATIC = "BRAINSTEM_STATIC"
    BRAINSTEM_DCML_PRE_LEARNING = "BRAINSTEM_DCML_PRE_LEARNING"
    BRAINSTEM_DCML_POST_LEARNING = "BRAINSTEM_DCML_POST_LEARNING"
    BRAINSTEM_DCML_ROLLBACK = "BRAINSTEM_DCML_ROLLBACK"
    BRAINSTEM_NATIVE_ONLY = "BRAINSTEM_NATIVE_ONLY"


class PublicationStatus(StrEnum):
    EXPERIMENTAL = "EXPERIMENTAL"
    INTERNAL_ONLY = "INTERNAL_ONLY"
    REPRODUCIBLE = "REPRODUCIBLE"
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"
    APPROVED_FOR_PUBLICATION = "APPROVED_FOR_PUBLICATION"
    RETRACTED = "RETRACTED"


class ToolPolicy(StrEnum):
    STANDARD = "STANDARD"
    NONSTANDARD = "NONSTANDARD"


class BenchmarkSpec(BaseModel):
    name: str
    slug: str
    category: EvaluationCategory = EvaluationCategory.EXTERNAL_FRONTIER_BENCHMARK
    domain: str
    version: str
    official_url: str
    license: str
    access_notes: str
    required_environment: list[str] = Field(default_factory=list)
    official_metrics: list[str]
    tool_policy: dict[str, Any]
    partitions: dict[str, str]
    default_status: AdapterStatus
    command_env: str


class SystemManifest(BaseModel):
    system_name: str
    configuration: Configuration
    brainstem_commit: str
    runtime_commit: str
    dcml_checkpoint: str | None = None
    attached_provider: str | None = None
    model_identifier: str | None = None
    provider_version: str | None = None
    adapter_version: str
    benchmark_version: str
    dataset_hash: str
    prompt_template_hash: str
    tool_configuration: dict[str, Any]
    inference_setting: str
    temperature: float | None = None
    seed: int
    token_budget: int
    time_budget_seconds: int
    cost_budget: float
    retry_budget: int
    hardware: str
    operating_system: str
    run_timestamp: str = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def honest_name(self) -> "SystemManifest":
        if (
            self.attached_provider
            and self.attached_provider.lower() not in self.system_name.lower()
        ):
            raise ValueError("system_name must identify the attached provider")
        if self.system_name.strip().upper() == "BRAINSTEM" and self.attached_provider:
            raise ValueError("attached-model results may not be named BRAINSTEM")
        return self


class Metrics(BaseModel):
    accuracy: float | None = None
    pass_at_1: float | None = None
    pass_at_k: dict[str, float] = Field(default_factory=dict)
    task_success_rate: float | None = None
    partial_credit_score: float | None = None
    wall_clock_seconds: float = 0
    token_usage: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    retries: int = 0
    estimated_cost: float = 0
    failures: int = 0
    timeouts: int = 0
    strategy_selection_regret: float | None = None
    routing_regret: float | None = None
    calibration_error: float | None = None
    intervention_rate: float | None = None
    recovery_rate: float | None = None
    verified_evidence_rate: float | None = None
    unsupported_claim_rate: float | None = None
    transfer_lift: float | None = None
    memory_contribution: float | None = None
    tool_selection_contribution: float | None = None
    attached_model_contribution: float | None = None
    dcml_policy_contribution: float | None = None


class RepeatedStatistics(BaseModel):
    count: int
    mean: float
    median: float
    standard_deviation: float
    confidence_interval_95: tuple[float, float]
    best: float
    worst: float
    failures: dict[str, int]


class BenchmarkResult(BaseModel):
    run_id: str
    benchmark: str
    category: EvaluationCategory = EvaluationCategory.EXTERNAL_FRONTIER_BENCHMARK
    configuration: Configuration
    status: str
    tool_policy: ToolPolicy
    official_score: bool
    metrics: Metrics
    repetitions: RepeatedStatistics | None = None
    contamination_status: str
    limitations: list[str]
    raw_result_hash: str

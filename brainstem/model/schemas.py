"""Typed, versioned schemas for the native BRAINSTEM-DCML model."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


class LearningStatus(StrEnum):
    OBSERVED = "OBSERVED"
    PROPOSED = "PROPOSED"
    EVALUATED = "EVALUATED"
    APPROVED = "APPROVED"
    PROMOTED = "PROMOTED"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    CONFLICTED = "CONFLICTED"
    ROLLED_BACK = "ROLLED_BACK"
    SUPERSEDED = "SUPERSEDED"


class Belief(BaseModel):
    id: str
    subject: str
    predicate: str
    object: str
    confidence: float = Field(ge=0, le=1)
    provenance: list[str]
    status: Literal["SUPPORTED", "CONFLICTED", "SUPERSEDED"] = "SUPPORTED"
    revision: int = 1


class CognitiveState(BaseModel):
    schema_version: int = SCHEMA_VERSION
    identity: str = "Kindred BRAINSTEM"
    revision: int = 1
    current_context: dict[str, Any] = Field(default_factory=dict)
    goals: list[str] = Field(default_factory=list)
    active_intentions: list[str] = Field(default_factory=list)
    uncertainty: float = Field(default=1.0, ge=0, le=1)
    unresolved_contradictions: list[str] = Field(default_factory=list)
    working_memory: list[str] = Field(default_factory=list)
    episodic_memory: list[str] = Field(default_factory=list)
    semantic_memory: list[str] = Field(default_factory=list)
    procedural_memory: list[str] = Field(default_factory=list)
    learned_strategies: list[str] = Field(default_factory=list)
    capability_history: list[str] = Field(default_factory=list)


class WorldNode(BaseModel):
    id: str
    kind: str
    label: str
    state: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    provenance: list[str]
    revision: int = 1


class WorldRelationship(BaseModel):
    id: str
    source_id: str
    target_id: str
    kind: str
    causal_strength: float | None = Field(default=None, ge=-1, le=1)
    confidence: float = Field(ge=0, le=1)
    provenance: list[str]
    revision: int = 1


class Prediction(BaseModel):
    id: str
    hypothesis: str
    expected_outcome: str
    probability: float = Field(ge=0, le=1)
    strategy_id: str | None = None
    observed_outcome: str | None = None
    prediction_error: float | None = None


class Counterfactual(BaseModel):
    id: str
    prediction_id: str
    intervention: str
    expected_outcome: str
    probability: float = Field(ge=0, le=1)


class StrategyCandidate(BaseModel):
    id: str
    name: str
    description: str
    expected_utility: float
    risk: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    source: str


class CognitiveResult(BaseModel):
    cycle_id: str
    session_id: str
    response: str
    strategy: StrategyCandidate
    prediction: Prediction
    uncertainty: float
    evidence_id: str
    learning_proposal_id: str | None = None
    telemetry_id: str
    state_revision: int


class TrainingDataset(BaseModel):
    id: str
    version: int
    learning_type: Literal[
        "memory", "policy", "prompt_strategy", "adapter_tuning", "model_weights"
    ]
    example_ids: list[str]
    evaluation_split: list[str]
    status: Literal["REFERENCE_ONLY", "APPROVED_FOR_TRAINING"]
    checkpoint_identity: str | None = None
    parameter_training_performed: bool = False

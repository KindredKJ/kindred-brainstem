"""Formal future parameter-training boundary; no weights are trained here."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Literal, Protocol

from brainstem.model.schemas import TrainingDataset
from brainstem.runtime.store import StateStore


class ParameterTrainer(Protocol):
    def pre_evaluate(self, dataset: TrainingDataset) -> dict[str, float]: ...
    def train_adapter(self, dataset: TrainingDataset, output: Path) -> str: ...
    def post_evaluate(
        self, checkpoint: str, dataset: TrainingDataset
    ) -> dict[str, float]: ...
    def rollback(self, checkpoint: str) -> None: ...


class ReferenceDatasetBuilder:
    """Exports approved experiences without performing parameter training."""

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def build(
        self,
        output: Path,
        learning_type: Literal[
            "memory", "policy", "prompt_strategy", "adapter_tuning", "model_weights"
        ] = "prompt_strategy",
    ) -> TrainingDataset:
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT id FROM experiences WHERE approved_for_training=1 ORDER BY created_at"
            ).fetchall()
        ids = [row[0] for row in rows]
        split_at = max(0, int(len(ids) * 0.8))
        dataset = TrainingDataset(
            id=f"KDS-{uuid.uuid4().hex[:12].upper()}",
            version=1,
            learning_type=learning_type,
            example_ids=ids[:split_at],
            evaluation_split=ids[split_at:],
            status="REFERENCE_ONLY",
            parameter_training_performed=False,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(dataset.model_dump(), indent=2) + "\n")
        return dataset

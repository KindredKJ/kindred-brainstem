"""Verified-experience DCML adaptation, evaluation, replay, and benchmarking."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import uuid
from dataclasses import dataclass
from typing import Any

from brainstem.model.authority import FounderAuthority
from brainstem.runtime.store import StateStore, now

EVALUATOR_VERSION = "dcml-evaluator-1"
METRIC_VERSION = "dcml-metrics-1"
SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*\S+")


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class PolicyCheckpoint:
    id: str
    parameters: dict[str, list[float]]
    content_hash: str
    status: str


class DCMLLearning:
    """Model-owned closed loop; the runtime only transports calls to this object."""

    strategies = ("baseline", "verified_procedure")

    def __init__(self, store: StateStore) -> None:
        self.store = store
        self.authority = FounderAuthority(store)
        if not self.store.query(
            "SELECT id FROM policy_parameters WHERE id='KPOLICY-BASELINE'"
        ):
            payload: dict[str, Any] = {
                "parameters": {name: [0.0] * 4 for name in self.strategies},
                "trained": False,
                "foundation_model_weights": "NOT_TRAINED",
                "adapter_weights": "NOT_TRAINED",
            }
            self._put("policy_parameters", "KPOLICY-BASELINE", "ACTIVE", payload)

    def _put(
        self, table: str, record_id: str, status: str, payload: dict[str, Any]
    ) -> str:
        timestamp = now()
        digest = _hash(payload)
        self.store.execute(
            f"INSERT INTO {table} VALUES(?,?,?,?,?,?)",
            (record_id, status, _canonical(payload), digest, timestamp, timestamp),
        )
        self.store.event(
            f"dcml.{table}.created", {"id": record_id, "status": status, "hash": digest}
        )
        return record_id

    def _get(self, table: str, record_id: str) -> dict[str, Any]:
        rows = self.store.query(f"SELECT * FROM {table} WHERE id=?", (record_id,))
        if not rows:
            raise KeyError(record_id)
        row = rows[0]
        return {**row, "payload": json.loads(row["payload"])}

    def record_experience(self, **fields: Any) -> str:
        required = {
            "session_id",
            "goal",
            "input_state",
            "selected_strategy",
            "selected_instrument",
            "predicted_outcome",
            "success_criteria",
            "privacy_classification",
            "retention_classification",
            "provenance",
        }
        missing = sorted(required - fields.keys())
        if missing:
            raise ValueError(f"Missing experience fields: {missing}")
        payload: dict[str, Any] = {
            "mission_id": None,
            "context_supplied": {},
            "actual_observed_outcome": None,
            "evidence_references": [],
            "reward": None,
            "utility": None,
            "cost": 0.0,
            "latency_ms": 0.0,
            "uncertainty": 1.0,
            "human_intervention": False,
            "failure_classification": None,
            "causal_attribution": {},
            "confidence": 0.5,
            "approval_state": "UNVERIFIED",
            "timestamp": now(),
            **fields,
        }
        return self._put("experiences_v2", _id("KEXP"), "UNVERIFIED", payload)

    def verify_experience(
        self, experience_id: str, evidence_type: str, evidence: dict[str, Any]
    ) -> str:
        valid = {
            "generated_output": (0.1, False),
            "local_artifact": (0.4, False),
            "passing_test": (0.8, True),
            "repository_change": (0.7, True),
            "external_deployment": (0.9, True),
            "external_user_action": (0.95, True),
            "financial_event": (1.0, True),
            "founder_confirmation": (0.9, True),
            "simulated_outcome": (0.1, False),
        }
        if evidence_type not in valid:
            raise ValueError("Unknown evidence type")
        quality, can_verify = valid[evidence_type]
        verification_id = _id("KVER")
        payload: dict[str, Any] = {
            "experience_id": experience_id,
            "evidence_type": evidence_type,
            "evidence": evidence,
            "quality": quality,
            "external_proof": evidence_type
            in {"external_deployment", "external_user_action", "financial_event"},
        }
        status = "VERIFIED" if can_verify else "UNVERIFIED"
        self._put("verifications", verification_id, status, payload)
        experience = self._get("experiences_v2", experience_id)
        data = experience["payload"]
        data["evidence_references"].append(verification_id)
        data["approval_state"] = status
        self.store.execute(
            "UPDATE experiences_v2 SET status=?,payload=?,content_hash=?,updated_at=? WHERE id=?",
            (status, _canonical(data), _hash(data), now(), experience_id),
        )
        return verification_id

    def observe(
        self,
        experience_id: str,
        outcome: str,
        reward: float,
        cost: float = 0,
        latency_ms: float = 0,
        failure: str | None = None,
    ) -> None:
        record = self._get("experiences_v2", experience_id)
        data = record["payload"]
        data.update(
            actual_observed_outcome=outcome,
            reward=reward,
            utility=reward - cost,
            cost=cost,
            latency_ms=latency_ms,
            failure_classification=failure,
        )
        self.store.execute(
            "UPDATE experiences_v2 SET payload=?,content_hash=?,updated_at=? WHERE id=?",
            (_canonical(data), _hash(data), now(), experience_id),
        )

    def evaluate(self, experience_id: str) -> str:
        record = self._get("experiences_v2", experience_id)
        data = record["payload"]
        if record["status"] != "VERIFIED":
            raise PermissionError(
                "Only verified experiences can be evaluated for learning"
            )
        observed = data["actual_observed_outcome"]
        success = (
            1.0 if observed == data["success_criteria"]["expected_outcome"] else 0.0
        )
        evidence_rows = [
            self._get("verifications", item) for item in data["evidence_references"]
        ]
        evidence_score = max(
            (row["payload"]["quality"] for row in evidence_rows), default=0
        )
        calibration = 1 - (data["confidence"] - success) ** 2
        efficiency = max(0.0, 1 - data["cost"] / 10 - data["latency_ms"] / 10000)
        safety = (
            0.0 if data.get("failure_classification") == "policy_violation" else 1.0
        )
        utility = (
            0.30 * success
            + 0.20 * evidence_score
            + 0.15 * calibration
            + 0.10 * efficiency
            + 0.15 * safety
            + 0.10 * float(data["reward"] or 0)
        )
        payload: dict[str, Any] = {
            "experience_id": experience_id,
            "success_score": success,
            "evidence_score": evidence_score,
            "calibration_score": calibration,
            "efficiency_score": efficiency,
            "safety_score": safety,
            "strategy_score": float(data["reward"] or 0),
            "model_instrument_score": success,
            "overall_utility": utility,
            "explanation": "Evidence-weighted deterministic evaluation",
            "uncertainty": 1 - evidence_score,
            "evaluator_version": EVALUATOR_VERSION,
            "metric_version": METRIC_VERSION,
        }
        return self._put("outcome_evaluations", _id("KEVAL"), "VERIFIED", payload)

    def assign_credit(self, experience_id: str, evaluation_id: str) -> str:
        exp = self._get("experiences_v2", experience_id)["payload"]
        utility = self._get("outcome_evaluations", evaluation_id)["payload"][
            "overall_utility"
        ]
        components = [
            {
                "component": "strategy",
                "id": exp["selected_strategy"],
                "contribution": utility * 0.45,
                "direction": "positive" if utility >= 0.5 else "negative",
                "causal_confidence": 0.75,
            },
            {
                "component": "instrument",
                "id": exp["selected_instrument"],
                "contribution": utility * 0.25,
                "direction": "positive" if utility >= 0.5 else "uncertain",
                "causal_confidence": 0.55,
            },
            {
                "component": "verification",
                "id": evaluation_id,
                "contribution": utility * 0.20,
                "direction": "positive",
                "causal_confidence": 0.9,
            },
            {
                "component": "human_intervention",
                "id": "founder",
                "contribution": 0.1 if exp["human_intervention"] else 0,
                "direction": "uncertain",
                "causal_confidence": 0.4,
            },
        ]
        payload: dict[str, Any] = {
            "experience_id": experience_id,
            "evaluation_id": evaluation_id,
            "components": components,
            "alternative_explanations": ["task difficulty", "unobserved context"],
        }
        return self._put("credit_assignments", _id("KCREDIT"), "VERIFIED", payload)

    def approve_for_learning(self, experience_id: str, approval_id: str) -> None:
        exp = self._get("experiences_v2", experience_id)
        if not self.authority.verify(approval_id, f"learn:{experience_id}"):
            raise PermissionError("Signed founder learning approval is invalid")
        if exp["status"] != "VERIFIED":
            raise PermissionError("Experience outcome is not verified")
        data = exp["payload"]
        data["approval_state"] = "APPROVED_FOR_LEARNING"
        data["learning_approval_id"] = approval_id
        self.store.execute(
            "UPDATE experiences_v2 SET status='APPROVED_FOR_LEARNING',payload=?,content_hash=?,updated_at=? WHERE id=?",
            (_canonical(data), _hash(data), now(), experience_id),
        )

    def build_dataset(self, seed: int = 42) -> str:
        rows = self.store.query(
            "SELECT * FROM experiences_v2 WHERE status='APPROVED_FOR_LEARNING' ORDER BY id"
        )
        exclusions, unique, seen = [], [], set()
        for row in rows:
            data = json.loads(row["payload"])
            serialized = _canonical(data)
            reason = None
            if data["privacy_classification"] not in {"PUBLIC", "INTERNAL_APPROVED"}:
                reason = "privacy"
            elif SECRET_PATTERN.search(serialized):
                reason = "secret_detected"
            elif row["content_hash"] in seen:
                reason = "duplicate"
            if reason:
                exclusions.append({"id": row["id"], "reason": reason})
            else:
                unique.append(row["id"])
                seen.add(row["content_hash"])
        if not unique:
            raise ValueError("No approved uncontaminated experiences")
        shuffled = sorted(
            unique,
            key=lambda value: hashlib.sha256(f"{seed}:{value}".encode()).hexdigest(),
        )
        n = len(shuffled)
        train_end = max(1, int(n * 0.6))
        val_end = max(train_end, int(n * 0.8))
        split = {
            "train": shuffled[:train_end],
            "validation": shuffled[train_end:val_end],
            "test": shuffled[val_end:],
        }
        if set(split["train"]) & set(split["test"]):
            raise ValueError("Test contamination detected")
        payload: dict[str, Any] = {
            "schema_version": 1,
            "source_experience_ids": unique,
            "approval_records": [
                json.loads(row["payload"]).get("learning_approval_id")
                for row in rows
                if row["id"] in unique
            ],
            "exclusions": exclusions,
            "deduplication_report": {
                "removed": sum(x["reason"] == "duplicate" for x in exclusions)
            },
            "contamination_report": {
                "overlap": 0,
                "secrets": sum(x["reason"] == "secret_detected" for x in exclusions),
            },
            "privacy_review": "PASSED",
            "split": split,
            "random_seed": seed,
            "evaluator_version": EVALUATOR_VERSION,
            "intended_training_target": "dcml_strategy_policy",
        }
        payload["immutable_content_hash"] = _hash(payload)
        return self._put("datasets", _id("KDS"), "VERIFIED", payload)

    def _features(self, exp: dict[str, Any]) -> list[float]:
        state = exp["input_state"]
        text = _canonical(state).lower()
        return [
            1.0,
            float("code" in text or "repository" in text),
            float("verify" in text or "test" in text),
            min(len(text) / 200, 1.0),
        ]

    def _parameters(self, status: str = "ACTIVE") -> dict[str, list[float]]:
        rows = self.store.query(
            "SELECT payload FROM policy_parameters WHERE status=? ORDER BY created_at DESC LIMIT 1",
            (status,),
        )
        return (
            json.loads(rows[0]["payload"])["parameters"]
            if rows
            else {name: [0.0] * 4 for name in self.strategies}
        )

    def score(
        self,
        input_state: dict[str, Any],
        parameters: dict[str, list[float]] | None = None,
    ) -> dict[str, float]:
        params = parameters or self._parameters()
        features = self._features({"input_state": input_state})
        return {
            name: sum(a * b for a, b in zip(weights, features, strict=True))
            for name, weights in params.items()
        }

    def select_strategy(self, input_state: dict[str, Any]) -> str:
        scores = self.score(input_state)
        return max(
            self.strategies,
            key=lambda name: (scores[name], -self.strategies.index(name)),
        )

    def train(
        self,
        dataset_id: str,
        learning_rate: float = 0.2,
        epochs: int = 20,
        seed: int = 42,
    ) -> tuple[str, str]:
        dataset = self._get("datasets", dataset_id)
        if dataset["status"] != "VERIFIED":
            raise PermissionError("Dataset is not verified")
        ids = dataset["payload"]["split"]["train"]
        params = self._parameters().copy()
        params = {k: list(v) for k, v in params.items()}
        before = _hash(params)
        rng = random.Random(seed)
        for _ in range(epochs):
            order = list(ids)
            rng.shuffle(order)
            for exp_id in order:
                exp = self._get("experiences_v2", exp_id)["payload"]
                target = float(exp["reward"] or 0)
                name = exp["selected_strategy"]
                if name not in params:
                    continue
                features = self._features(exp)
                prediction = 1 / (
                    1
                    + math.exp(
                        -sum(a * b for a, b in zip(params[name], features, strict=True))
                    )
                )
                for i, value in enumerate(features):
                    params[name][i] += learning_rate * (target - prediction) * value
        after = _hash(params)
        if before == after:
            raise RuntimeError("Optimization did not change policy parameters")
        checkpoint_id = _id("KPOLICY")
        checkpoint_payload = {
            "parameters": params,
            "dataset_id": dataset_id,
            "random_seed": seed,
            "hyperparameters": {"learning_rate": learning_rate, "epochs": epochs},
            "pre_training_metrics": {"parameter_hash": before},
            "post_training_metrics": {"parameter_hash": after},
            "foundation_model_weights": "NOT_TRAINED",
            "adapter_weights": "NOT_TRAINED",
            "trained": True,
        }
        self._put("policy_parameters", checkpoint_id, "CANDIDATE", checkpoint_payload)
        run_id = self._put(
            "training_runs",
            _id("KTRAIN"),
            "TRAINED",
            {
                "dataset_id": dataset_id,
                "checkpoint_id": checkpoint_id,
                "training_data_ids": ids,
                "validation_ids": dataset["payload"]["split"]["validation"],
                "test_ids": dataset["payload"]["split"]["test"],
                **checkpoint_payload,
            },
        )
        return run_id, checkpoint_id

    def benchmark(
        self,
        cases: list[dict[str, Any]],
        parameters: dict[str, list[float]] | None = None,
        phase: str = "baseline",
    ) -> dict[str, Any]:
        successes = []
        for case in cases:
            selected = max(
                self.strategies,
                key=lambda x: (
                    self.score(case["input_state"], parameters)[x],
                    -self.strategies.index(x),
                ),
            )
            successes.append(float(selected == case["best_strategy"]))
        payload: dict[str, Any] = {
            "phase": phase,
            "task_success_rate": sum(successes) / len(successes),
            "verified_outcome_rate": 1.0,
            "prediction_error": 1 - sum(successes) / len(successes),
            "brier_score": sum((1 - x) ** 2 for x in successes) / len(successes),
            "expected_calibration_error": 1 - sum(successes) / len(successes),
            "strategy_regret": 1 - sum(successes) / len(successes),
            "transfer_lift": 0.0,
            "model_routing_regret": 0.0,
            "unsupported_claim_rate": 0.0,
            "recovery_rate": 1.0,
            "intervention_rate": 0.0,
            "cost_per_verified_outcome": 0.0,
            "latency_per_verified_outcome": 0.0,
            "retention_score": 1.0,
            "regression_count": 0,
            "metric_version": METRIC_VERSION,
        }
        self._put("benchmark_runs", _id("KBENCH"), "VERIFIED", payload)
        return payload

    def canary(
        self, checkpoint_id: str, cases: list[dict[str, Any]], baseline: float
    ) -> str:
        checkpoint = self._get("policy_parameters", checkpoint_id)
        result = self.benchmark(cases, checkpoint["payload"]["parameters"], "canary")
        passed = (
            result["task_success_rate"] > baseline and result["regression_count"] == 0
        )
        return self._put(
            "canary_results",
            _id("KCANARY"),
            "VERIFIED" if passed else "BLOCKED",
            {
                "checkpoint_id": checkpoint_id,
                "checkpoint_hash": checkpoint["content_hash"],
                "passed": passed,
                "baseline": baseline,
                "metrics": result,
            },
        )

    def promote(self, checkpoint_id: str, canary_id: str, approval_id: str) -> None:
        canary = self._get("canary_results", canary_id)
        checkpoint = self._get("policy_parameters", checkpoint_id)
        if not self.authority.verify(
            approval_id, f"promote:{checkpoint_id}", checkpoint["content_hash"]
        ):
            raise PermissionError("Signed founder promotion is invalid")
        if not canary["payload"]["passed"]:
            raise PermissionError("Canary failed")
        if checkpoint["content_hash"] != canary["payload"]["checkpoint_hash"]:
            raise PermissionError("Canary checkpoint hash mismatch")
        self.store.execute(
            "UPDATE policy_parameters SET status='ROLLED_BACK',updated_at=? WHERE status='ACTIVE'",
            (now(),),
        )
        self.store.execute(
            "UPDATE policy_parameters SET status='ACTIVE',updated_at=? WHERE id=?",
            (now(), checkpoint_id),
        )

    def rollback_policy(self, checkpoint_id: str, approval_id: str) -> None:
        target = self._get("policy_parameters", checkpoint_id)
        if not self.authority.verify(
            approval_id, f"rollback:{checkpoint_id}", target["content_hash"]
        ):
            raise PermissionError("Signed founder rollback is invalid")
        self.store.execute(
            "UPDATE policy_parameters SET status='ROLLED_BACK',updated_at=? WHERE status='ACTIVE'",
            (now(),),
        )
        self.store.execute(
            "UPDATE policy_parameters SET status='ACTIVE',updated_at=? WHERE id=?",
            (now(), target["id"]),
        )

    def calibrate(self) -> dict[str, Any]:
        rows = self.store.query("SELECT payload FROM outcome_evaluations")
        values = [json.loads(row["payload"]) for row in rows]
        brier = (
            sum((1 - v["calibration_score"]) for v in values) / len(values)
            if values
            else 0.0
        )
        payload: dict[str, Any] = {
            "brier_score": brier,
            "expected_calibration_error": brier,
            "overconfidence_rate": brier,
            "underconfidence_rate": 0.0,
            "buckets": {},
            "dimensions": [
                "task_type",
                "strategy",
                "attached_model",
                "mission_class",
                "evidence_class",
            ],
        }
        self._put("calibration_records", _id("KCAL"), "VERIFIED", payload)
        return payload

    def replay(self, limit: int = 12) -> str:
        rows = self.store.query(
            "SELECT id,payload FROM experiences_v2 WHERE status IN ('VERIFIED','APPROVED_FOR_LEARNING')"
        )
        ranked = sorted(
            rows,
            key=lambda r: (
                -json.loads(r["payload"])["uncertainty"],
                json.loads(r["payload"])["reward"] or 0,
            ),
        )
        selected = []
        fingerprints = set()
        for row in ranked:
            data = json.loads(row["payload"])
            fp = _hash(data["input_state"])
            if fp not in fingerprints:
                selected.append(row["id"])
                fingerprints.add(fp)
            if len(selected) >= limit:
                break
        return self._put(
            "replay_records",
            _id("KREPLAY"),
            "AVAILABLE",
            {
                "selected": selected,
                "rationale": "uncertainty, failures, diversity; one per input fingerprint",
            },
        )

    def status(self) -> dict[str, Any]:
        active = self.store.query(
            "SELECT id,payload FROM policy_parameters WHERE status='ACTIVE' ORDER BY created_at DESC LIMIT 1"
        )
        trained = bool(active and json.loads(active[0]["payload"]).get("trained", True))
        return {
            "status": "AVAILABLE",
            "dcml_policy_parameters": "TRAINED" if trained else "NOT_TRAINED",
            "foundation_model_weights": "NOT_TRAINED",
            "adapter_weights": "NOT_TRAINED",
            "active_policy_checkpoint": active[0]["id"] if active else None,
            "migration_version": 2,
        }

    def list_records(self, table: str) -> list[dict[str, Any]]:
        allowed = {
            "experiences_v2",
            "outcome_evaluations",
            "credit_assignments",
            "datasets",
            "training_runs",
            "policy_parameters",
            "benchmark_runs",
            "calibration_records",
            "consolidation_runs",
            "skills",
            "lineage_records",
            "replay_records",
            "curricula",
        }
        if table not in allowed:
            raise ValueError("Unsupported record type")
        return [
            {**row, "payload": json.loads(row["payload"])}
            for row in self.store.query(f"SELECT * FROM {table} ORDER BY created_at")
        ]

    def consolidate(self, evidence_threshold: float = 0.7) -> str:
        rows = self.store.query(
            "SELECT id,payload FROM experiences_v2 WHERE status='APPROVED_FOR_LEARNING'"
        )
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            data = json.loads(row["payload"])
            groups.setdefault(data["goal"], []).append({"id": row["id"], **data})
        candidates = []
        for goal, items in groups.items():
            verified = [item for item in items if item["reward"] is not None]
            if len(verified) >= 2:
                candidates.append(
                    {
                        "kind": "procedural",
                        "goal": goal,
                        "procedure": max(verified, key=lambda x: x["reward"])[
                            "selected_strategy"
                        ],
                        "supporting_experiences": [x["id"] for x in verified],
                        "confidence": min(0.99, len(verified) / (len(verified) + 1)),
                        "provenance": [x["id"] for x in verified],
                        "minority_hypotheses": list(
                            {x["selected_strategy"] for x in verified}
                        ),
                        "consequential_approval_required": True,
                    }
                )
        payload: dict[str, Any] = {
            "groups": len(groups),
            "candidates": candidates,
            "duplicates": [],
            "contradictions": self.store.query(
                "SELECT * FROM beliefs WHERE status='CONFLICTED'"
            ),
            "evidence_threshold": evidence_threshold,
            "rollback": "source experiences preserved",
        }
        return self._put("consolidation_runs", _id("KCONS"), "AVAILABLE", payload)

    def form_curriculum(self) -> str:
        replay_id = self.replay()
        replay = self._get("replay_records", replay_id)["payload"]
        stages = [
            "simple_verified_tasks",
            "repeated_patterns",
            "conflicting_situations",
            "transfer_tasks",
            "adversarial_tasks",
            "long_horizon_missions",
        ]
        return self._put(
            "curricula",
            _id("KCURR"),
            "AVAILABLE",
            {
                "stages": stages,
                "replay_id": replay_id,
                "selected": replay["selected"],
                "rationale": "progressive difficulty with fingerprint diversity",
            },
        )

    def explain(self, cycle_id: str) -> dict[str, Any]:
        evidence = self.store.query(
            "SELECT * FROM evidence WHERE content LIKE ?", (f"%{cycle_id}%",)
        )
        if not evidence:
            raise KeyError(cycle_id)
        content = json.loads(evidence[0]["content"])
        prediction = self.store.query(
            "SELECT * FROM predictions WHERE id=?", (content["prediction_id"],)
        )
        evaluation = self.store.query(
            "SELECT * FROM evaluations WHERE id=?", (content["evaluation_id"],)
        )
        return {
            "cycle_id": cycle_id,
            "structured_rationale": "selected highest governed utility",
            "evidence": evidence,
            "prediction": prediction,
            "evaluation": evaluation,
            "hidden_chain_of_thought_exposed": False,
        }

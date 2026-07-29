"""Executable advanced DCML mechanisms with governed, inspectable records."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections import defaultdict
from typing import Any, Callable

from brainstem.runtime.store import StateStore, now


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


class AdvancedDCML:
    """Model-owned transfer, causal, routing, mission, skill, and diagnosis logic."""

    def __init__(
        self,
        store: StateStore,
        propose: Callable[[str, dict[str, Any], list[str], bool], str] | None = None,
    ) -> None:
        self.store = store
        self.propose = propose

    def _put(
        self, table: str, record_id: str, status: str, payload: dict[str, Any]
    ) -> str:
        timestamp = now()
        self.store.execute(
            f"INSERT INTO {table} VALUES(?,?,?,?,?,?)",
            (
                record_id,
                status,
                _canonical(payload),
                _hash(payload),
                timestamp,
                timestamp,
            ),
        )
        return record_id

    def _get(self, table: str, record_id: str) -> dict[str, Any]:
        rows = self.store.query(f"SELECT * FROM {table} WHERE id=?", (record_id,))
        if not rows:
            raise KeyError(record_id)
        return {**rows[0], "payload": json.loads(rows[0]["payload"])}

    def structural_features(self, observation: Any, prefix: str = "root") -> set[str]:
        features: set[str] = set()
        if isinstance(observation, dict):
            features.add(f"{prefix}:mapping")
            for key, value in sorted(observation.items()):
                features.add(f"{prefix}.field:{key}:{type(value).__name__}")
                features |= self.structural_features(value, f"{prefix}.{key}")
        elif isinstance(observation, list):
            features.add(f"{prefix}:sequence")
            for value in observation[:10]:
                features |= self.structural_features(value, f"{prefix}.item")
        elif isinstance(observation, str):
            features.add(f"{prefix}:text")
            if "\n" in observation:
                features.add(f"{prefix}:multiline")
            if any(token in observation for token in ("def ", "class ", "function ")):
                features.add(f"{prefix}:source_code")
        else:
            features.add(f"{prefix}:{type(observation).__name__}")
        return features

    def form_concept(
        self,
        label: str,
        experience_ids: list[str],
        counterexamples: list[str] | None = None,
    ) -> str:
        if len(experience_ids) < 2:
            raise ValueError("concept formation requires repeated verified experiences")
        supports = []
        shared: set[str] | None = None
        provenance = []
        for experience_id in experience_ids:
            rows = self.store.query(
                "SELECT * FROM experiences_v2 WHERE id=? AND status='APPROVED_FOR_LEARNING'",
                (experience_id,),
            )
            if not rows:
                raise PermissionError(f"experience {experience_id} is not approved")
            data = json.loads(rows[0]["payload"])
            features = self.structural_features(data["input_state"])
            shared = features if shared is None else shared & features
            supports.append(experience_id)
            provenance.extend(data.get("provenance", []))
        payload = {
            "label": label,
            "supporting_experiences": supports,
            "features": sorted(shared or set()),
            "relationships": [],
            "abstraction": "shared structural input contract",
            "confidence": len(shared or set())
            / max(
                1,
                len(
                    set().union(
                        *(
                            self.structural_features(
                                json.loads(
                                    self.store.query(
                                        "SELECT payload FROM experiences_v2 WHERE id=?",
                                        (i,),
                                    )[0]["payload"]
                                )["input_state"]
                            )
                            for i in experience_ids
                        )
                    )
                ),
            ),
            "provenance": sorted(set(provenance)),
            "counterexamples": counterexamples or [],
            "revision_history": [
                {"revision": 1, "reason": "initial verified abstraction"}
            ],
        }
        return self._put("concepts", _id("KCONCEPT"), "AVAILABLE", payload)

    def transfer_evaluate(
        self,
        concept_id: str,
        target: Any,
        threshold: float = 0.65,
        baseline_score: float = 0.0,
        applied_score: float = 0.0,
    ) -> dict[str, Any]:
        concept = self._get("concepts", concept_id)["payload"]
        source = set(concept["features"])
        target_features = self.structural_features(target)
        similarity = len(source & target_features) / max(
            1, len(source | target_features)
        )
        uncertainty = 1 - similarity
        applicable = similarity >= threshold
        lift = applied_score - baseline_score if applicable else 0.0
        payload = {
            "concept_id": concept_id,
            "target_features": sorted(target_features),
            "structural_similarity": similarity,
            "threshold": threshold,
            "uncertainty": uncertainty,
            "applicable": applicable,
            "baseline_score": baseline_score,
            "applied_score": applied_score,
            "transfer_lift": lift,
            "keyword_similarity_used": False,
        }
        record_id = self._put(
            "transfer_evaluations", _id("KTRANSFER"), "VERIFIED", payload
        )
        return {"id": record_id, **payload}

    def create_causal_hypothesis(
        self,
        cause: str,
        effect: str,
        confounders: list[str],
        alternatives: list[str],
        expected_effect: float,
    ) -> str:
        payload = {
            "cause": cause,
            "effect": effect,
            "confounders": confounders,
            "alternative_causes": alternatives,
            "expected_effect": expected_effect,
            "observations": [],
            "causal_confidence": 0.5,
            "falsification_evidence": [],
            "revision": 1,
            "classification": "HYPOTHESIS_NOT_VERIFIED_CAUSATION",
        }
        return self._put("causal_hypotheses", _id("KCAUSE"), "AVAILABLE", payload)

    def intervene(
        self,
        hypothesis_id: str,
        intervention: str,
        observed_effect: float,
        controlled_confounders: list[str],
        evidence: list[str],
    ) -> dict[str, Any]:
        record = self._get("causal_hypotheses", hypothesis_id)
        data = record["payload"]
        uncontrolled = set(data["confounders"]) - set(controlled_confounders)
        error = abs(data["expected_effect"] - observed_effect)
        delta = (0.15 if error <= 0.2 else -0.25) * (1 / (1 + len(uncontrolled)))
        confidence = max(0, min(1, data["causal_confidence"] + delta))
        outcome = (
            "STRENGTHENED"
            if delta > 0
            else ("REJECTED" if confidence < 0.2 else "WEAKENED")
        )
        if delta < 0:
            data["falsification_evidence"].extend(evidence)
        data["causal_confidence"] = confidence
        data["revision"] += 1
        data["observations"].append(
            {
                "intervention": intervention,
                "observed_effect": observed_effect,
                "controlled_confounders": controlled_confounders,
                "uncontrolled_confounders": sorted(uncontrolled),
                "evidence": evidence,
                "prediction_error": error,
                "revision_outcome": outcome,
            }
        )
        self.store.execute(
            "UPDATE causal_hypotheses SET status=?,payload=?,content_hash=?,updated_at=? WHERE id=?",
            (outcome, _canonical(data), _hash(data), now(), hypothesis_id),
        )
        intervention_id = self._put(
            "interventions",
            _id("KINT"),
            "VERIFIED",
            {"hypothesis_id": hypothesis_id, **data["observations"][-1]},
        )
        return {
            "intervention_id": intervention_id,
            "status": outcome,
            "causal_confidence": confidence,
        }

    def counterfactual_decide(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        if len(candidates) < 2:
            raise ValueError("counterfactual comparison requires alternatives")
        scored = []
        for item in candidates:
            score = (
                item["expected_success"]
                - item["risk"]
                - 0.1 * item["expected_cost"]
                - 0.001 * item["expected_latency_ms"]
                + 0.05 * float(item["reversible"])
                - item["uncertainty"] * 0.2
            )
            scored.append({**item, "decision_score": score})
        chosen = max(scored, key=lambda x: x["decision_score"])
        payload = {
            "chosen_strategy": chosen["strategy"],
            "rejected_alternatives": [x for x in scored if x is not chosen],
            "candidates": scored,
            "decision_rationale": "maximum evidence-aware reversible utility",
            "actual_outcome": None,
            "counterfactual_regret": None,
        }
        decision_id = self._put(
            "counterfactual_decisions", _id("KDECIDE"), "AVAILABLE", payload
        )
        return {"id": decision_id, **payload}

    def observe_counterfactual(
        self,
        decision_id: str,
        actual_utility: float,
        alternative_observations: dict[str, float],
    ) -> dict[str, Any]:
        record = self._get("counterfactual_decisions", decision_id)
        data = record["payload"]
        best_alternative = max(
            alternative_observations.values(), default=actual_utility
        )
        regret = max(0, best_alternative - actual_utility)
        data.update(
            actual_outcome=actual_utility,
            counterfactual_regret=regret,
            alternative_observations=alternative_observations,
        )
        self.store.execute(
            "UPDATE counterfactual_decisions SET status='VERIFIED',payload=?,content_hash=?,updated_at=? WHERE id=?",
            (_canonical(data), _hash(data), now(), decision_id),
        )
        observation_id = self._put(
            "counterfactual_observations",
            _id("KREGRET"),
            "VERIFIED",
            {
                "decision_id": decision_id,
                "actual_utility": actual_utility,
                "best_alternative": best_alternative,
                "regret": regret,
            },
        )
        proposal_id = None
        if regret > 0 and self.propose:
            proposal_id = self.propose(
                "counterfactual_regret",
                {"decision_id": decision_id, "regret": regret},
                [observation_id],
                False,
            )
        return {
            "id": observation_id,
            "counterfactual_regret": regret,
            "learning_proposal_id": proposal_id,
        }

    def update_model_profile(
        self,
        model_id: str,
        task_type: str,
        success: float,
        latency_ms: float,
        cost: float,
        confidence: float,
        evidence_class: str,
    ) -> str:
        rows = self.store.query(
            "SELECT * FROM model_performance_profiles WHERE status='AVAILABLE'"
        )
        current = None
        for row in rows:
            data = json.loads(row["payload"])
            if data["model_id"] == model_id and data["task_type"] == task_type:
                current = (row, data)
                break
        observations = [] if current is None else current[1]["observations"]
        observations.append(
            {
                "success": success,
                "latency_ms": latency_ms,
                "cost": cost,
                "confidence": confidence,
                "evidence_class": evidence_class,
            }
        )
        n = len(observations)
        payload = {
            "model_id": model_id,
            "task_type": task_type,
            "observations": observations,
            "historical_success": sum(x["success"] for x in observations) / n,
            "latency_ms": sum(x["latency_ms"] for x in observations) / n,
            "cost": sum(x["cost"] for x in observations) / n,
            "calibration_error": sum(
                abs(x["confidence"] - x["success"]) for x in observations
            )
            / n,
        }
        if current:
            self.store.execute(
                "UPDATE model_performance_profiles SET payload=?,content_hash=?,updated_at=? WHERE id=?",
                (_canonical(payload), _hash(payload), now(), current[0]["id"]),
            )
            return current[0]["id"]
        return self._put(
            "model_performance_profiles", _id("KPROFILE"), "AVAILABLE", payload
        )

    def route_model(
        self,
        task_type: str,
        candidates: list[dict[str, Any]],
        privacy: str,
        risk: float,
        cost_budget: float,
        latency_budget_ms: float,
    ) -> dict[str, Any]:
        profiles = {}
        for row in self.store.query("SELECT payload FROM model_performance_profiles"):
            data = json.loads(row["payload"])
            profiles[(data["model_id"], data["task_type"])] = data
        eligible = []
        for item in candidates:
            profile = profiles.get((item["model_id"], task_type), {})
            reasons = []
            if item["health"] != "HEALTHY":
                reasons.append("unhealthy")
            if privacy not in item["privacy_classes"]:
                reasons.append("privacy")
            if item["cost"] > cost_budget:
                reasons.append("cost")
            if item["latency_ms"] > latency_budget_ms:
                reasons.append("latency")
            if risk > item["max_risk"]:
                reasons.append("risk")
            score = (
                profile.get("historical_success", 0.5)
                - profile.get("calibration_error", 0.5)
                - item["cost"] * 0.1
                - item["latency_ms"] * 0.0001
            )
            if not reasons:
                eligible.append((score, item))
        if not eligible:
            raise RuntimeError(
                "no explicitly permitted healthy model route; no fallback"
            )
        selected = max(eligible, key=lambda x: x[0])[1]
        payload = {
            "task_type": task_type,
            "selected_model": selected["model_id"],
            "candidate_count": len(candidates),
            "privacy": privacy,
            "risk": risk,
            "cost_budget": cost_budget,
            "latency_budget_ms": latency_budget_ms,
            "rationale": "health, privacy, risk, budget, latency, historical success, calibration",
            "silent_fallback": False,
        }
        route_id = self._put("routing_decisions", _id("KROUTE"), "AVAILABLE", payload)
        return {"id": route_id, **payload}

    def metacognitive_review(
        self,
        cycle_id: str,
        confidence: float,
        observed_correctness: float,
        evidence: list[str],
        assumptions: list[str],
        context_items: int,
        retrieved_items: int,
        contradictions: int,
        goal_alignment: float,
        verification_complete: bool,
    ) -> dict[str, Any]:
        calibration_error = abs(confidence - observed_correctness)
        diagnosis = {
            "cycle_id": cycle_id,
            "confidence_calibration": calibration_error,
            "missing_evidence": not bool(evidence),
            "unsupported_assumptions": assumptions,
            "context_loss": context_items > 0 and retrieved_items == 0,
            "retrieval_quality": retrieved_items / max(1, context_items),
            "contradiction_handling": "REVIEW_REQUIRED"
            if contradictions
            else "AVAILABLE",
            "overconfidence": confidence - observed_correctness > 0.2,
            "underconfidence": observed_correctness - confidence > 0.2,
            "goal_drift": goal_alignment < 0.7,
            "incomplete_verification": not verification_complete,
            "human_review_required": bool(assumptions)
            or not verification_complete
            or contradictions > 0,
        }
        review_id = self._put(
            "metacognitive_reviews", _id("KMETA"), "VERIFIED", diagnosis
        )
        proposal_id = None
        if diagnosis["human_review_required"] and self.propose:
            proposal_id = self.propose(
                "metacognitive_diagnosis", diagnosis, [review_id], False
            )
        diagnosis["id"] = review_id
        diagnosis["learning_proposal_id"] = proposal_id
        return diagnosis

    def create_skill(
        self,
        name: str,
        purpose: str,
        inputs: list[str],
        outputs: list[str],
        preconditions: list[str],
        steps: list[str],
        tool_requirements: list[str],
        model_requirements: list[str],
        evidence_requirements: list[str],
        failure_modes: list[str],
        provenance: list[str],
        approval_id: str,
    ) -> str:
        payload = {
            "name": name,
            "purpose": purpose,
            "inputs": inputs,
            "outputs": outputs,
            "preconditions": preconditions,
            "steps": steps,
            "tool_requirements": tool_requirements,
            "model_requirements": model_requirements,
            "evidence_requirements": evidence_requirements,
            "known_failure_modes": failure_modes,
            "success_history": [],
            "confidence": 0.5,
            "provenance": provenance,
            "version": 1,
            "approval_state": "APPROVED",
            "approval_id": approval_id,
            "rollback_state": "AVAILABLE",
        }
        return self._put("skill_records", _id("KSKILL"), "APPROVED", payload)

    def create_mission(
        self,
        objective: str,
        success_criteria: list[str],
        constraints: list[str],
        plan: list[str],
        dependencies: list[str],
    ) -> str:
        payload = {
            "objective": objective,
            "success_criteria": success_criteria,
            "constraints": constraints,
            "plan": plan,
            "dependencies": dependencies,
            "strategies": [],
            "predictions": [],
            "approvals": [],
            "actions": [],
            "evidence": [],
            "outcomes": [],
            "failures": [],
            "lessons": [],
            "completion_status": "IN_PROGRESS",
        }
        return self._put("missions_v2", _id("KMISSION"), "AVAILABLE", payload)

    def record_mission_stage(
        self,
        mission_id: str,
        stage: int,
        action: str,
        strategy: str,
        prediction: float,
        evidence: list[str],
    ) -> str:
        self._get("missions_v2", mission_id)
        return self._put(
            "mission_stages",
            _id("KSTAGE"),
            "OBSERVED",
            {
                "mission_id": mission_id,
                "stage": stage,
                "action": action,
                "strategy": strategy,
                "prediction": prediction,
                "evidence": evidence,
                "delayed_reward": None,
            },
        )

    def complete_mission(
        self, mission_id: str, outcome: str, reward: float, evidence: list[str]
    ) -> list[str]:
        mission = self._get("missions_v2", mission_id)
        data = mission["payload"]
        data["outcomes"].append(outcome)
        data["evidence"].extend(evidence)
        data["completion_status"] = "COMPLETED"
        self.store.execute(
            "UPDATE missions_v2 SET status='VERIFIED',payload=?,content_hash=?,updated_at=? WHERE id=?",
            (_canonical(data), _hash(data), now(), mission_id),
        )
        stages = self.store.query(
            "SELECT * FROM mission_stages WHERE payload LIKE ? ORDER BY created_at",
            (f'%"mission_id":"{mission_id}"%',),
        )
        if not stages:
            return []
        weights = [math.exp(-0.25 * (len(stages) - 1 - i)) for i in range(len(stages))]
        total = sum(weights)
        ids = []
        for row, weight in zip(stages, weights, strict=True):
            stage = json.loads(row["payload"])
            credit = reward * weight / total
            ids.append(
                self._put(
                    "temporal_credit",
                    _id("KTEMP"),
                    "VERIFIED",
                    {
                        "mission_id": mission_id,
                        "stage_id": row["id"],
                        "strategy": stage["strategy"],
                        "delayed_reward": credit,
                        "evidence": evidence,
                        "method": "exponential temporal attribution",
                    },
                )
            )
        return ids

    def calibrate_dimensions(
        self, observations: list[dict[str, Any]]
    ) -> dict[str, Any]:
        dimensions = (
            "task_type",
            "strategy",
            "model_id",
            "mission_class",
            "evidence_class",
        )
        grouped: dict[str, dict[str, list[tuple[float, float]]]] = {
            dimension: defaultdict(list) for dimension in dimensions
        }
        for item in observations:
            for dimension in dimensions:
                grouped[dimension][str(item[dimension])].append(
                    (
                        float(item["predicted_confidence"]),
                        float(item["observed_correctness"]),
                    )
                )
        results: dict[str, Any] = {}
        for dimension, groups in grouped.items():
            results[dimension] = {}
            for label, values in groups.items():
                brier = sum(
                    (predicted - observed) ** 2 for predicted, observed in values
                ) / len(values)
                buckets = defaultdict(list)
                for predicted, observed in values:
                    buckets[min(9, int(predicted * 10))].append((predicted, observed))
                ece = sum(
                    len(entries)
                    / len(values)
                    * abs(
                        sum(x[0] for x in entries) / len(entries)
                        - sum(x[1] for x in entries) / len(entries)
                    )
                    for entries in buckets.values()
                )
                results[dimension][label] = {
                    "brier_score": brier,
                    "expected_calibration_error": ece,
                    "overconfidence_rate": sum(p - o > 0.2 for p, o in values)
                    / len(values),
                    "underconfidence_rate": sum(o - p > 0.2 for p, o in values)
                    / len(values),
                    "count": len(values),
                }
        payload = {"dimensions": results, "observation_count": len(observations)}
        record_id = self._put(
            "calibration_records", _id("KCALADV"), "VERIFIED", payload
        )
        return {"id": record_id, **payload}

    def benchmark_suite(self, results: dict[str, float], phase: str) -> dict[str, Any]:
        categories = (
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
        )
        missing = [category for category in categories if category not in results]
        if missing:
            raise ValueError(f"missing benchmark categories: {missing}")
        payload = {
            "phase": phase,
            "categories": {key: float(results[key]) for key in categories},
            "task_success_rate": sum(results[key] for key in categories)
            / len(categories),
            "regression_count": sum(results[key] < 0.8 for key in categories),
            "verified": True,
        }
        record_id = self._put(
            "advanced_benchmark_runs", _id("KBENCHADV"), "VERIFIED", payload
        )
        return {"id": record_id, **payload}

"""Native BRAINSTEM model and fused Deep Cognitive Model Learning cycle."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from typing import Any

from brainstem.adapters.models import ModelAdapter
from brainstem.model.dcml import DCMLLearning
from brainstem.model.schemas import (
    Belief,
    CognitiveResult,
    CognitiveState,
    Counterfactual,
    LearningStatus,
    Prediction,
    StrategyCandidate,
    WorldNode,
    WorldRelationship,
)
from brainstem.runtime.store import IdempotencyConflict, StateStore, now

_ALLOWED_TRANSITIONS = {
    LearningStatus.OBSERVED: {LearningStatus.PROPOSED, LearningStatus.REJECTED},
    LearningStatus.PROPOSED: {
        LearningStatus.EVALUATED,
        LearningStatus.REJECTED,
        LearningStatus.CONFLICTED,
    },
    LearningStatus.EVALUATED: {
        LearningStatus.APPROVED,
        LearningStatus.REJECTED,
        LearningStatus.CONFLICTED,
    },
    LearningStatus.APPROVED: {LearningStatus.PROMOTED, LearningStatus.REJECTED},
    LearningStatus.PROMOTED: {LearningStatus.ACTIVE, LearningStatus.ROLLED_BACK},
    LearningStatus.ACTIVE: {LearningStatus.ROLLED_BACK, LearningStatus.SUPERSEDED},
}


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


class BrainstemModel:
    """BRAINSTEM itself: persistent cognition, DCML, governance, and instruments."""

    state_id = "KINDRED-BRAINSTEM"

    def __init__(
        self, store: StateStore, instruments: dict[str, ModelAdapter] | None = None
    ) -> None:
        self.store = store
        self.instruments = instruments or {}
        self.environment = os.getenv("KINDRED_ENVIRONMENT", "local")
        self.tenant = os.getenv("KINDRED_TENANT", "default")
        self._ensure_state()
        self.dcml = DCMLLearning(store)

    def _ensure_state(self) -> None:
        if self.store.query(
            "SELECT id FROM cognitive_states WHERE id=?", (self.state_id,)
        ):
            return
        state = CognitiveState()
        timestamp = now()
        self.store.execute(
            "INSERT INTO cognitive_states VALUES(?,?,?,?,?,?)",
            (
                self.state_id,
                state.schema_version,
                state.revision,
                state.model_dump_json(),
                timestamp,
                timestamp,
            ),
        )
        self.store.event(
            "cognitive_state.created", {"model": self.state_id, "revision": 1}
        )

    def inspect_state(self) -> CognitiveState:
        row = self.store.query(
            "SELECT payload FROM cognitive_states WHERE id=?", (self.state_id,)
        )[0]
        return CognitiveState.model_validate_json(row["payload"])

    def _save_state(self, state: CognitiveState) -> None:
        self.store.execute(
            "UPDATE cognitive_states SET schema_version=?, revision=?, payload=?, updated_at=? WHERE id=?",
            (
                state.schema_version,
                state.revision,
                state.model_dump_json(),
                now(),
                self.state_id,
            ),
        )
        self.store.event("cognitive_state.revised", {"revision": state.revision})

    def perceive(
        self, session_id: str, input_text: str, context: dict[str, Any] | None = None
    ) -> str:
        experience_id = _id("KEXP")
        self.store.execute(
            "INSERT INTO experiences VALUES(?,?,?,?,?,?,?)",
            (
                experience_id,
                session_id,
                input_text,
                json.dumps(context or {}, sort_keys=True),
                None,
                0,
                now(),
            ),
        )
        self.store.event(
            "dcml.perceived", {"experience_id": experience_id, "session_id": session_id}
        )
        return experience_id

    def recall(self, query: str, limit: int = 8) -> dict[str, list[dict[str, Any]]]:
        pattern = f"%{query.lower()}%"
        beliefs = self.store.query(
            "SELECT * FROM beliefs WHERE lower(subject || ' ' || predicate || ' ' || object) LIKE ? ORDER BY confidence DESC LIMIT ?",
            (pattern, limit),
        )
        memories = self.store.query(
            "SELECT * FROM memory WHERE lower(content) LIKE ? ORDER BY created_at DESC LIMIT ?",
            (pattern, limit),
        )
        experiences = self.store.query(
            "SELECT id,input,result,created_at FROM experiences WHERE lower(input) LIKE ? ORDER BY created_at DESC LIMIT ?",
            (pattern, limit),
        )
        return {"beliefs": beliefs, "memories": memories, "experiences": experiences}

    def add_belief(
        self,
        subject: str,
        predicate: str,
        object_: str,
        confidence: float,
        provenance: list[str],
    ) -> Belief:
        belief = Belief(
            id=_id("KBLF"),
            subject=subject,
            predicate=predicate,
            object=object_,
            confidence=confidence,
            provenance=provenance,
        )
        conflicts = self.store.query(
            "SELECT id,object FROM beliefs WHERE subject=? AND predicate=? AND object<>? AND status='SUPPORTED'",
            (subject, predicate, object_),
        )
        if conflicts:
            belief.status = "CONFLICTED"
            ids = [row["id"] for row in conflicts]
            placeholders = ",".join("?" for _ in ids)
            self.store.execute(
                f"UPDATE beliefs SET status='CONFLICTED' WHERE id IN ({placeholders})",  # noqa: S608 -- placeholders only; values remain parameterized
                tuple(ids),
            )
            state = self.inspect_state()
            state.unresolved_contradictions.append(
                f"{subject}:{predicate}:{','.join(row['object'] for row in conflicts)}|{object_}"
            )
            state.revision += 1
            self._save_state(state)
        self.store.execute(
            "INSERT INTO beliefs VALUES(?,?,?,?,?,?,?,?,?)",
            (
                belief.id,
                subject,
                predicate,
                object_,
                confidence,
                json.dumps(provenance),
                belief.status,
                1,
                now(),
            ),
        )
        return belief

    def beliefs(self) -> list[dict[str, Any]]:
        return self.store.query("SELECT * FROM beliefs ORDER BY created_at")

    def add_world_node(self, node: WorldNode) -> None:
        self.store.execute(
            "INSERT INTO world_nodes VALUES(?,?,?,?,?,?,?,?)",
            (
                node.id,
                node.kind,
                node.label,
                json.dumps(node.state),
                node.confidence,
                json.dumps(node.provenance),
                node.revision,
                now(),
            ),
        )

    def add_world_relationship(self, relation: WorldRelationship) -> None:
        self.store.execute(
            "INSERT INTO world_relationships VALUES(?,?,?,?,?,?,?,?,?)",
            (
                relation.id,
                relation.source_id,
                relation.target_id,
                relation.kind,
                relation.causal_strength,
                relation.confidence,
                json.dumps(relation.provenance),
                relation.revision,
                now(),
            ),
        )

    def world(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "nodes": self.store.query("SELECT * FROM world_nodes"),
            "relationships": self.store.query("SELECT * FROM world_relationships"),
            "revision_history": self.store.query(
                "SELECT * FROM events WHERE kind LIKE 'world.%'"
            ),
        }

    def reason(
        self, input_text: str, recalled: dict[str, Any]
    ) -> list[StrategyCandidate]:
        active = self.store.query(
            "SELECT * FROM strategies WHERE status='ACTIVE' ORDER BY expected_utility DESC"
        )
        candidates = [
            StrategyCandidate(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                expected_utility=row["expected_utility"],
                risk=row["risk"],
                confidence=row["confidence"],
                source="learned",
            )
            for row in active
        ]
        policy_choice = self.dcml.select_strategy({"text": input_text})
        if policy_choice == "verified_procedure":
            candidates.append(
                StrategyCandidate(
                    id="KSTR-DCML-POLICY",
                    name="verified_procedure",
                    description="Numerically trained DCML policy selected the verified procedure.",
                    expected_utility=0.95,
                    risk=0.1,
                    confidence=0.9,
                    source="dcml_policy",
                )
            )
        candidates.append(
            StrategyCandidate(
                id="KSTR-BASELINE",
                name="evidence_grounded_response",
                description="Use selected session context and request evidence for unsupported conclusions.",
                expected_utility=0.55 + min(len(recalled["beliefs"]), 5) * 0.02,
                risk=0.2,
                confidence=0.6,
                source="native_dcml",
            )
        )
        return candidates

    def simulate(
        self, strategy: StrategyCandidate, input_text: str
    ) -> tuple[Prediction, Counterfactual]:
        prediction = Prediction(
            id=_id("KPRED"),
            hypothesis=f"Using {strategy.name} addresses the request",
            expected_outcome="useful_response",
            probability=strategy.confidence,
            strategy_id=strategy.id,
        )
        counterfactual = Counterfactual(
            id=_id("KCF"),
            prediction_id=prediction.id,
            intervention=f"Do not use {strategy.name}",
            expected_outcome="lower_evidence_alignment",
            probability=max(0.0, 1 - strategy.confidence),
        )
        self.store.execute(
            "INSERT INTO predictions VALUES(?,?,?,?,?,?,?,?)",
            (
                prediction.id,
                prediction.hypothesis,
                prediction.expected_outcome,
                prediction.probability,
                prediction.strategy_id,
                None,
                None,
                now(),
            ),
        )
        self.store.execute(
            "INSERT INTO counterfactuals VALUES(?,?,?,?,?,?)",
            (
                counterfactual.id,
                prediction.id,
                counterfactual.intervention,
                counterfactual.expected_outcome,
                counterfactual.probability,
                now(),
            ),
        )
        return prediction, counterfactual

    def decide(self, candidates: list[StrategyCandidate]) -> StrategyCandidate:
        return max(
            candidates,
            key=lambda item: item.expected_utility * item.confidence - item.risk,
        )

    def _frame_task(
        self,
        session_id: str,
        text: str,
        strategy: StrategyCandidate,
        recalled: dict[str, Any],
    ) -> list[dict[str, str]]:
        system = {
            "owner": "Kindred BRAINSTEM",
            "instrument_role": "subordinate specialist",
            "strategy": strategy.name,
            "selected_context": recalled,
            "permissions": ["generate_response"],
            "tool_boundaries": "adapter-declared capabilities only",
            "expected_output": "clean assistant response",
        }
        history = [
            {"role": row["role"], "content": row["content"]}
            for row in self.store.history(session_id)
        ]
        return [
            {"role": "system", "content": json.dumps(system, sort_keys=True)},
            *history,
            {"role": "user", "content": text},
        ]

    def act(
        self,
        session_id: str,
        instrument: str,
        text: str,
        strategy: StrategyCandidate,
        recalled: dict[str, Any],
    ) -> tuple[str, str]:
        if instrument not in self.instruments:
            raise KeyError(f"Unknown cognitive instrument: {instrument}")
        adapter = self.instruments[instrument]
        telemetry_id = _id("KTEL")
        messages = self._frame_task(session_id, text, strategy, recalled)
        try:
            generation = adapter.generate(messages)
        except Exception as exc:
            self.store.execute(
                "INSERT INTO telemetry VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    telemetry_id,
                    session_id,
                    instrument,
                    "DEGRADED",
                    "[]",
                    json.dumps([str(exc)]),
                    "{}",
                    "[]",
                    now(),
                ),
            )
            self.store.event(
                "instrument.failed",
                {"telemetry_id": telemetry_id, "instrument": instrument},
            )
            raise
        telemetry = generation.telemetry
        self.store.execute(
            "INSERT INTO telemetry VALUES(?,?,?,?,?,?,?,?,?)",
            (
                telemetry_id,
                session_id,
                instrument,
                "VERIFIED",
                json.dumps(telemetry.get("commands", [])),
                "[]",
                json.dumps(generation.usage),
                json.dumps(telemetry.get("execution_events", [])),
                now(),
            ),
        )
        return generation.text, telemetry_id

    def reflect(
        self, experience_id: str, prediction: Prediction, response: str
    ) -> tuple[str, float]:
        success = 1.0 if response.strip() else 0.0
        error = abs(success - prediction.probability)
        evaluation_id = _id("KEVAL")
        failures = [] if success else ["empty_response"]
        self.store.execute(
            "INSERT INTO evaluations VALUES(?,?,?,?,?,?,?,?)",
            (
                evaluation_id,
                experience_id,
                prediction.id,
                success,
                error,
                json.dumps(failures),
                json.dumps([]),
                now(),
            ),
        )
        self.store.execute(
            "UPDATE predictions SET observed_outcome=?, prediction_error=? WHERE id=?",
            ("useful_response" if success else "empty_response", error, prediction.id),
        )
        return evaluation_id, error

    def learn(
        self,
        kind: str,
        payload: dict[str, Any],
        provenance: list[str],
        consequential: bool = True,
    ) -> str:
        learning_id = _id("KLP")
        timestamp = now()
        self.store.execute(
            "INSERT INTO learning_proposals VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                learning_id,
                kind,
                json.dumps(payload, sort_keys=True),
                LearningStatus.OBSERVED,
                int(consequential),
                json.dumps(provenance),
                None,
                None,
                None,
                1,
                timestamp,
                timestamp,
            ),
        )
        self.store.event(
            "dcml.learning_observed", {"learning_id": learning_id, "kind": kind}
        )
        self._transition_learning(learning_id, LearningStatus.PROPOSED)
        return learning_id

    def route_instrument(
        self,
        text: str,
        privacy: str = "INTERNAL",
        risk: float = 0.3,
        cost_budget: float = 1.0,
        latency_budget_ms: float = 120000,
    ) -> str:
        candidates = []
        for model_id, adapter in self.instruments.items():
            health = adapter.health()
            candidates.append(
                {
                    "model_id": model_id,
                    "health": health.status,
                    "privacy_classes": getattr(
                        adapter, "privacy_classes", ["PUBLIC", "INTERNAL"]
                    ),
                    "cost": float(getattr(adapter, "estimated_cost", 0.0)),
                    "latency_ms": float(getattr(adapter, "estimated_latency_ms", 1000)),
                    "max_risk": float(getattr(adapter, "max_risk", 0.5)),
                    "capabilities": sorted(adapter.capabilities()),
                }
            )
        route = self.dcml.advanced.route_model(
            "code"
            if any(token in text.lower() for token in ("code", "repository", "test"))
            else "general",
            candidates,
            privacy,
            risk,
            cost_budget,
            latency_budget_ms,
        )
        return str(route["selected_model"])

    def cognitive_cycle(
        self,
        session_id: str,
        text: str,
        instrument: str,
        context: dict[str, Any] | None = None,
    ) -> CognitiveResult:
        cycle_id = _id("KCYCLE")
        if instrument == "auto":
            instrument = self.route_instrument(text)
        experience_id = self.perceive(session_id, text, context)
        recalled = self.recall(text)
        candidates = self.reason(text, recalled)
        strategy = self.decide(candidates)
        prediction, _ = self.simulate(strategy, text)
        try:
            response, telemetry_id = self.act(
                session_id, instrument, text, strategy, recalled
            )
        except Exception:
            self.store.execute(
                "UPDATE experiences SET result=? WHERE id=?",
                (json.dumps({"status": "instrument_failure"}), experience_id),
            )
            raise
        evaluation_id, error = self.reflect(experience_id, prediction, response)
        proposal_id = None
        if error >= 0.25:
            proposal_id = self.learn(
                "strategy_evaluation",
                {"strategy": strategy.model_dump(), "prediction_error": error},
                [experience_id, evaluation_id],
                consequential=False,
            )
        self.store.execute(
            "UPDATE experiences SET result=? WHERE id=?",
            (
                json.dumps({"response": response, "evaluation_id": evaluation_id}),
                experience_id,
            ),
        )
        evidence_id = self.store.add_evidence(
            session_id,
            "dcml_cycle",
            {
                "cycle_id": cycle_id,
                "experience_id": experience_id,
                "prediction_id": prediction.id,
                "evaluation_id": evaluation_id,
            },
        )
        state = self.inspect_state()
        state.current_context = context or {}
        state.working_memory = [text, response]
        state.episodic_memory.append(experience_id)
        state.capability_history.append(instrument)
        state.uncertainty = error
        state.revision += 1
        self._save_state(state)
        return CognitiveResult(
            cycle_id=cycle_id,
            session_id=session_id,
            response=response,
            strategy=strategy,
            prediction=prediction,
            uncertainty=error,
            evidence_id=evidence_id,
            learning_proposal_id=proposal_id,
            telemetry_id=telemetry_id,
            state_revision=state.revision,
        )

    def observe_outcome(self, prediction_id: str, outcome: str) -> dict[str, Any]:
        rows = self.store.query(
            "SELECT * FROM predictions WHERE id=?", (prediction_id,)
        )
        if not rows:
            raise KeyError(prediction_id)
        prediction = rows[0]
        observed_success = 1.0 if outcome == prediction["expected_outcome"] else 0.0
        error = abs(observed_success - prediction["probability"])
        self.store.execute(
            "UPDATE predictions SET observed_outcome=?, prediction_error=? WHERE id=?",
            (outcome, error, prediction_id),
        )
        proposal_id = (
            self.learn(
                "prediction_error",
                {
                    "prediction_id": prediction_id,
                    "expected": prediction["expected_outcome"],
                    "observed": outcome,
                    "error": error,
                },
                [prediction_id],
                consequential=False,
            )
            if error > 0
            else None
        )
        return {
            "prediction_id": prediction_id,
            "observed_outcome": outcome,
            "prediction_error": error,
            "learning_proposal_id": proposal_id,
        }

    def learning(self, learning_id: str | None = None) -> list[dict[str, Any]]:
        if learning_id:
            return self.store.query(
                "SELECT * FROM learning_proposals WHERE id=?", (learning_id,)
            )
        return self.store.query("SELECT * FROM learning_proposals ORDER BY created_at")

    @staticmethod
    def _learning_digest(row: dict[str, Any]) -> str:
        immutable = {
            name: row[name]
            for name in ("id", "kind", "payload", "consequential", "provenance")
        }
        serialized = json.dumps(immutable, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode()).hexdigest()

    def _wait_for_decision(self, approval_id: str, request_hash: str) -> dict[str, Any]:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            submission = self.store.submission("learning-decision", approval_id)
            if submission and submission["request_hash"] != request_hash:
                raise PermissionError(
                    "Decision identity was rebound to different content"
                )
            if submission and submission["status"] == "COMPLETED":
                if not submission["response"]:
                    raise PermissionError(
                        "Completed decision is missing its durable response"
                    )
                return json.loads(submission["response"])
            if submission and submission["status"] == "FAILED":
                raise PermissionError("Prior decision submission failed closed")
            time.sleep(0.01)
        raise PermissionError("Matching decision submission is still processing")

    def _claim_decision(
        self,
        approval_id: str,
        learning_id: str,
        action: str,
        digest: str,
        decision: str,
    ) -> tuple[bool, dict[str, Any] | None, str]:
        request_hash = hashlib.sha256(
            json.dumps(
                {
                    "approval_id": approval_id,
                    "learning_id": learning_id,
                    "action": action,
                    "payload_digest": digest,
                    "environment": self.environment,
                    "tenant": self.tenant,
                    "decision": decision,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        try:
            status, stored_response = self.store.claim_submission(
                "learning-decision", approval_id, learning_id, request_hash
            )
        except IdempotencyConflict as exc:
            raise PermissionError(
                "Decision identity was rebound to different content"
            ) from exc
        if status == "CLAIMED":
            return True, None, request_hash
        if status == "COMPLETED":
            if stored_response is None:
                raise PermissionError(
                    "Completed decision is missing its durable response"
                )
            return False, stored_response, request_hash
        if status == "PROCESSING":
            return (
                False,
                self._wait_for_decision(approval_id, request_hash),
                request_hash,
            )
        raise PermissionError("Prior decision submission failed closed")

    def _transition_learning(
        self,
        learning_id: str,
        target: LearningStatus,
        evaluation: dict[str, Any] | None = None,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            selected = db.execute(
                "SELECT * FROM learning_proposals WHERE id=?", (learning_id,)
            ).fetchone()
            if selected is None:
                raise KeyError(learning_id)
            row = dict(selected)
            current = LearningStatus(row["status"])
            if target not in _ALLOWED_TRANSITIONS.get(current, set()):
                raise ValueError(f"Invalid learning transition {current} -> {target}")
            updated = db.execute(
                "UPDATE learning_proposals SET status=?, evaluation=COALESCE(?,evaluation), "
                "approval_id=COALESCE(?,approval_id), revision=revision+1, updated_at=? "
                "WHERE id=? AND status=? AND revision=?",
                (
                    target,
                    json.dumps(evaluation) if evaluation else None,
                    approval_id,
                    now(),
                    learning_id,
                    current,
                    row["revision"],
                ),
            )
            if updated.rowcount != 1:
                raise ValueError("Concurrent learning transition rejected")
        self.store.event(
            "dcml.learning_transition",
            {"learning_id": learning_id, "from": current, "to": target},
        )
        return self.learning(learning_id)[0]

    def evaluate_learning(
        self, learning_id: str, score: float, evidence: list[str]
    ) -> dict[str, Any]:
        return self._transition_learning(
            learning_id,
            LearningStatus.EVALUATED,
            {"score": score, "evidence": evidence},
        )

    def approve_learning(self, learning_id: str, approval_id: str) -> dict[str, Any]:
        rows = self.learning(learning_id)
        if not rows:
            raise KeyError(learning_id)
        digest = self._learning_digest(rows[0])
        action = f"learning:approve:{learning_id}"
        claimed, prior, _ = self._claim_decision(
            approval_id, learning_id, action, digest, "APPROVED"
        )
        if not claimed:
            if prior is None:
                raise PermissionError("Decision result was not durably available")
            return prior
        try:
            if not self.dcml.authority.authorize(
                approval_id,
                action,
                digest,
                expected_environment=self.environment,
                expected_tenant=self.tenant,
                expected_scope="learning-governance",
            ):
                raise PermissionError("Cryptographic founder approval is invalid")
            self.store.execute(
                "INSERT OR IGNORE INTO approvals VALUES(?,?,?,?,?)",
                (
                    approval_id,
                    action,
                    "APPROVED",
                    self.dcml.authority.key_id(),
                    now(),
                ),
            )
            result = self._transition_learning(
                learning_id, LearningStatus.APPROVED, approval_id=approval_id
            )
            self.store.complete_submission("learning-decision", approval_id, result)
            return result
        except Exception as exc:
            self.store.fail_submission(
                "learning-decision", approval_id, type(exc).__name__
            )
            raise

    def reject_learning(self, learning_id: str, approval_id: str) -> dict[str, Any]:
        rows = self.learning(learning_id)
        if not rows:
            raise KeyError(learning_id)
        digest = self._learning_digest(rows[0])
        action = f"learning:reject:{learning_id}"
        claimed, prior, _ = self._claim_decision(
            approval_id, learning_id, action, digest, "REJECTED"
        )
        if not claimed:
            if prior is None:
                raise PermissionError("Decision result was not durably available")
            return prior
        try:
            if not self.dcml.authority.authorize(
                approval_id,
                action,
                digest,
                expected_environment=self.environment,
                expected_tenant=self.tenant,
                expected_scope="learning-governance",
                expected_decision="REJECTED",
            ):
                raise PermissionError("Cryptographic founder rejection is invalid")
            result = self._transition_learning(learning_id, LearningStatus.REJECTED)
            self.store.complete_submission("learning-decision", approval_id, result)
            return result
        except Exception as exc:
            self.store.fail_submission(
                "learning-decision", approval_id, type(exc).__name__
            )
            raise

    def _authorize_learning_execution(
        self,
        row: dict[str, Any],
        approval_id: str,
        action: str,
        required_status: LearningStatus,
    ) -> None:
        if LearningStatus(row["status"]) != required_status:
            raise ValueError(
                f"Learning must be {required_status} before {action} execution"
            )
        if not self.dcml.authority.authorize(
            approval_id,
            f"learning:{action}:{row['id']}",
            self._learning_digest(row),
            expected_environment=self.environment,
            expected_tenant=self.tenant,
            expected_scope="learning-execution",
        ):
            raise PermissionError(
                f"Live cryptographic founder {action} approval is required"
            )

    def promote_learning(self, learning_id: str, approval_id: str) -> dict[str, Any]:
        rows = self.learning(learning_id)
        if not rows:
            raise KeyError(learning_id)
        digest = self._learning_digest(rows[0])
        action = f"learning:promote:{learning_id}"
        claimed, prior, _ = self._claim_decision(
            approval_id, learning_id, action, digest, "APPROVED"
        )
        if not claimed:
            if prior is None:
                raise PermissionError("Decision result was not durably available")
            return prior
        try:
            self._authorize_learning_execution(
                rows[0], approval_id, "promote", LearningStatus.APPROVED
            )
            row = self._transition_learning(learning_id, LearningStatus.PROMOTED)
            payload = json.loads(row["payload"])
            if row["kind"] in {"strategy", "strategy_evaluation"}:
                strategy = payload.get("strategy", payload)
                strategy_id = strategy.get("id", _id("KSTR"))
                self.store.execute(
                    "INSERT OR REPLACE INTO strategies VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        strategy_id,
                        strategy.get("name", "learned_strategy"),
                        strategy.get(
                            "description", "Founder-approved learned strategy"
                        ),
                        strategy.get("expected_utility", 0.8),
                        strategy.get("risk", 0.2),
                        strategy.get("confidence", 0.8),
                        "dcml_learning",
                        "PROMOTED",
                        learning_id,
                        1,
                        now(),
                    ),
                )
            elif row["kind"] == "memory":
                self.store.execute(
                    "INSERT INTO memory VALUES(?,?,?,?,?,?)",
                    (
                        _id("KMEM"),
                        payload.get("memory_type", "semantic"),
                        payload.get("content", ""),
                        "PROMOTED",
                        learning_id,
                        now(),
                    ),
                )
            elif row["kind"] in {"skill", "routing_policy", "procedure"}:
                self.store.execute(
                    "INSERT INTO skills VALUES(?,?,?,?,?,?,?)",
                    (
                        _id("KSKILL"),
                        payload.get("name", row["kind"]),
                        payload.get("procedure", json.dumps(payload)),
                        "PROMOTED",
                        json.dumps([learning_id]),
                        1,
                        now(),
                    ),
                )
            self.store.complete_submission("learning-decision", approval_id, row)
            return row
        except Exception as exc:
            self.store.fail_submission(
                "learning-decision", approval_id, type(exc).__name__
            )
            raise

    def activate_learning(self, learning_id: str, approval_id: str) -> dict[str, Any]:
        rows = self.learning(learning_id)
        if not rows:
            raise KeyError(learning_id)
        digest = self._learning_digest(rows[0])
        action = f"learning:activate:{learning_id}"
        claimed, prior, _ = self._claim_decision(
            approval_id, learning_id, action, digest, "APPROVED"
        )
        if not claimed:
            if prior is None:
                raise PermissionError("Decision result was not durably available")
            return prior
        try:
            self._authorize_learning_execution(
                rows[0], approval_id, "activate", LearningStatus.PROMOTED
            )
            row = self._transition_learning(learning_id, LearningStatus.ACTIVE)
            self.store.execute(
                "UPDATE strategies SET status='ACTIVE' WHERE learning_id=?",
                (learning_id,),
            )
            self.store.execute(
                "UPDATE memory SET status='ACTIVE' WHERE evidence_id=?",
                (learning_id,),
            )
            self.store.execute(
                "UPDATE skills SET status='ACTIVE' WHERE provenance LIKE ?",
                (f"%{learning_id}%",),
            )
            state = self.inspect_state()
            state.learned_strategies.extend(
                row_["id"]
                for row_ in self.store.query(
                    "SELECT id FROM strategies WHERE learning_id=?", (learning_id,)
                )
            )
            state.revision += 1
            self._save_state(state)
            self.store.complete_submission("learning-decision", approval_id, row)
            return row
        except Exception as exc:
            self.store.fail_submission(
                "learning-decision", approval_id, type(exc).__name__
            )
            raise

    def rollback_learning(self, learning_id: str, approval_id: str) -> dict[str, Any]:
        rows = self.learning(learning_id)
        if not rows:
            raise KeyError(learning_id)
        digest = self._learning_digest(rows[0])
        if not self.dcml.authority.authorize(
            approval_id,
            f"learning:rollback:{learning_id}",
            digest,
            expected_environment=self.environment,
            expected_tenant=self.tenant,
            expected_scope="learning-rollback",
        ):
            raise PermissionError("Signed founder learning rollback is invalid")
        row = self._transition_learning(learning_id, LearningStatus.ROLLED_BACK)
        self.store.execute(
            "UPDATE strategies SET status='ROLLED_BACK' WHERE learning_id=?",
            (learning_id,),
        )
        self.store.execute(
            "UPDATE memory SET status='ROLLED_BACK' WHERE evidence_id=?", (learning_id,)
        )
        self.store.execute(
            "UPDATE skills SET status='ROLLED_BACK' WHERE provenance LIKE ?",
            (f"%{learning_id}%",),
        )
        state = self.inspect_state()
        rolled_back = {
            item["id"]
            for item in self.store.query(
                "SELECT id FROM strategies WHERE learning_id=?", (learning_id,)
            )
        }
        state.learned_strategies = [
            item for item in state.learned_strategies if item not in rolled_back
        ]
        state.revision += 1
        self._save_state(state)
        return row

    def strategies(self) -> list[dict[str, Any]]:
        return self.store.query("SELECT * FROM strategies ORDER BY created_at")

    def skills(self) -> list[dict[str, Any]]:
        return self.store.query("SELECT * FROM skills ORDER BY created_at")

    def telemetry(self) -> list[dict[str, Any]]:
        return self.store.query("SELECT * FROM telemetry ORDER BY created_at")

    def checkpoint(self) -> str:
        checkpoint_id = _id("KCHK")
        snapshot: dict[str, Any] = {
            "state": self.inspect_state().model_dump(),
            "strategies": self.strategies(),
            "learning": self.learning(),
            "parameter_weights": "NOT_TRAINED",
        }
        self.store.execute(
            "INSERT INTO model_checkpoints VALUES(?,?,?,?,?)",
            (
                checkpoint_id,
                snapshot["state"]["revision"],
                json.dumps(snapshot, sort_keys=True),
                None,
                now(),
            ),
        )
        self.store.event("dcml.checkpoint_created", {"checkpoint_id": checkpoint_id})
        return checkpoint_id

    def rollback(self, checkpoint_id: str, approval_id: str) -> CognitiveState:
        rows = self.store.query(
            "SELECT snapshot FROM model_checkpoints WHERE id=?", (checkpoint_id,)
        )
        if not rows:
            raise KeyError(checkpoint_id)
        snapshot_digest = hashlib.sha256(rows[0]["snapshot"].encode()).hexdigest()
        if not self.dcml.authority.authorize(
            approval_id,
            f"cognitive:rollback:{checkpoint_id}",
            snapshot_digest,
            expected_environment=self.environment,
            expected_tenant=self.tenant,
            expected_scope="cognitive-rollback",
        ):
            raise PermissionError("Signed founder checkpoint rollback is invalid")
        snapshot = json.loads(rows[0]["snapshot"])
        state = CognitiveState.model_validate(snapshot["state"])
        state.revision += 1
        self._save_state(state)
        self.store.execute(
            "UPDATE strategies SET status='ROLLED_BACK' WHERE status='ACTIVE'"
        )
        for strategy in snapshot["strategies"]:
            self.store.execute(
                "UPDATE strategies SET status=? WHERE id=?",
                (strategy["status"], strategy["id"]),
            )
        self.store.event(
            "dcml.checkpoint_rolled_back", {"checkpoint_id": checkpoint_id}
        )
        return state

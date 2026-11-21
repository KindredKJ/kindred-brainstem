"""Native BRAINSTEM model and fused Deep Cognitive Model Learning cycle."""

from __future__ import annotations

import hashlib
import json
import re
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
from brainstem.runtime.store import StateStore, now

FOUNDER = "Kindred Jermaine Cox"
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
                f"UPDATE beliefs SET status='CONFLICTED' WHERE id IN ({placeholders})",
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
        # Generation is not outcome verification. It remains pending until
        # explicit criteria/evidence are evaluated by DCML.
        success = 0.0
        error = abs(success - prediction.probability)
        evaluation_id = _id("KEVAL")
        failures = ["outcome_not_verified"]
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
            ("pending_verification", error, prediction.id),
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

    def native_cycle(
        self,
        session_id: str,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run BRAINSTEM's existing DCML cognition without a generation instrument.

        This is actual stateful, structured policy inference: recall, select a
        learned/baseline strategy, predict, compare a counterfactual, and record
        evidence. It does NOT claim to synthesize open-ended language or verify
        the predicted real-world outcome.
        """
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise ValueError("native DCML objective must be 1-2000 characters")
        if context is not None and (
            not isinstance(context, dict)
            or len(json.dumps(context, sort_keys=True).encode("utf-8")) > 8192
        ):
            raise ValueError("native DCML context must be a small JSON object")
        cycle_id = _id("KCYCLE")
        # Recall BEFORE recording this input, so it cannot recall itself as
        # previous experience and inflate its own memory-evidence count.
        recalled = self.recall(text)
        candidates = self.reason(text, recalled)
        strategy = self.decide(candidates)
        experience_id = self.perceive(session_id, text, context)
        prediction, counterfactual = self.simulate(strategy, text)
        self.store.execute(
            "UPDATE experiences SET result=? WHERE id=?",
            (
                json.dumps(
                    {
                        "status": "prediction_pending_verification",
                        "mode": "native_structured_dcml",
                        "strategy_id": strategy.id,
                        "prediction_id": prediction.id,
                        "counterfactual_id": counterfactual.id,
                    },
                    sort_keys=True,
                ),
                experience_id,
            ),
        )
        evidence_id = self.store.add_evidence(
            session_id,
            "dcml_native_policy_cycle",
            {
                "cycle_id": cycle_id,
                "experience_id": experience_id,
                "strategy_id": strategy.id,
                "prediction_id": prediction.id,
                "counterfactual_id": counterfactual.id,
                "instrument": None,
                "outcome_verified": False,
            },
            status="OBSERVED_LOCAL",
        )
        state = self.inspect_state()
        state.current_context = context or {}
        state.working_memory = [text]
        state.episodic_memory.append(experience_id)
        state.capability_history.append("native_dcml_policy")
        state.uncertainty = 1.0 - strategy.confidence
        state.revision += 1
        self._save_state(state)
        self.store.event(
            "dcml.native_cycle",
            {
                "cycle_id": cycle_id,
                "session_id": session_id,
                "evidence_id": evidence_id,
                "state_revision": state.revision,
                "external_instrument_used": False,
                "external_outcome_verified": False,
            },
        )
        return {
            "schema": "kindred.brainstem.native-dcml.v1",
            "model_identity": self.state_id,
            "cycle_id": cycle_id,
            "session_id": session_id,
            "strategy": strategy.model_dump(),
            "prediction": prediction.model_dump(),
            "counterfactual": counterfactual.model_dump(),
            "recalled": {
                kind: len(recalled[kind])
                for kind in ("beliefs", "memories", "experiences")
            },
            "evidence_id": evidence_id,
            "state_revision": state.revision,
            "uncertainty_estimate": state.uncertainty,
            "inference_mode": "native_structured_policy",
            "external_instrument_used": False,
            "language_generation_performed": False,
            "external_outcome_verified": False,
            "learning_status": "not_evaluated",
        }

    def select_native_tool(
        self,
        session_id: str,
        objective: str,
        tools: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Let native DCML choose among *observed* read tools, not wing presets.

        The inference is deterministic evidence-weighted tool matching using
        the existing DCML counterfactual decision and persistent outcome data.
        It is native policy inference, not an LLM or an external tool call.
        """
        if not isinstance(objective, str) or not 1 <= len(objective.strip()) <= 1200:
            raise ValueError("objective must be 1-1200 characters")
        if not isinstance(tools, list) or not 2 <= len(tools) <= 12:
            raise ValueError("provide 2-12 live read-capability candidates")
        if context is not None and (
            not isinstance(context, dict)
            or len(json.dumps(context, sort_keys=True).encode()) > 8192
        ):
            raise ValueError("tool decision context must be a small JSON object")
        names: set[str] = set()
        for item in tools:
            if (
                not isinstance(item, dict)
                or set(item) != {"name", "description", "risk"}
                or not isinstance(item["name"], str)
                or not re.fullmatch(r"[a-z][a-z0-9._-]{3,110}", item["name"])
                or not isinstance(item["description"], str)
                or not 4 <= len(item["description"]) <= 600
                or item["risk"] != "read"
                or item["name"] in names
            ):
                raise ValueError("tool candidates must be unique typed read capabilities")
            names.add(item["name"])

        def terms(value: str) -> set[str]:
            ignore = {"the", "this", "that", "and", "for", "from",
                      "with", "kindred", "labs", "wing", "look", "review",
                      "read", "list", "find", "latest", "recent", "open",
                      "all", "get", "check", "about", "actual", "our"}
            words = re.findall(r"[a-z0-9]+", value.lower())
            return {
                (word[:-1] if word.endswith("s") and len(word) > 4 else word)
                for word in words if word not in ignore and len(word) > 2
            }

        objective_terms = terms(objective)
        if not objective_terms:
            raise ValueError("objective lacks distinctive tool-selection terms")
        # Recall from persisted *observed* tool outcomes, not fabricated
        # counterfactual results. The original BRAINSTEM records stay canonical.
        historical = self.store.query(
            """SELECT payload FROM counterfactual_decisions
               WHERE status='VERIFIED' ORDER BY updated_at DESC LIMIT 300"""
        )
        outcomes: dict[str, list[float]] = {}
        for row in historical:
            data = json.loads(row["payload"])
            tool_name = data.get("chosen_strategy")
            utility = data.get("actual_outcome")
            if tool_name in names and isinstance(utility, (int, float)):
                outcomes.setdefault(tool_name, []).append(float(utility))
        scored: list[dict[str, Any]] = []
        for item in sorted(tools, key=lambda x: x["name"]):
            name = item["name"]
            candidate_terms = terms(name + " " + item["description"])
            overlap = len(candidate_terms & objective_terms)
            relevance = overlap / max(1, len(objective_terms))
            prior = outcomes.get(name, [])
            # A bounded empirical adjustment makes later choices respond to
            # actual observed API execution rather than to model rhetoric.
            empirical = (sum(prior) / len(prior)) if prior else 0.5
            expected = max(
                0.05, min(0.98, 0.35 + 0.52 * relevance
                          + (0.28 * (empirical - 0.5) if prior else 0)),
            )
            scored.append({
                "strategy": name,
                "expected_success": expected,
                "risk": 0.02,
                "expected_cost": 0.0,
                "expected_latency_ms": 50.0,
                "reversible": True,
                "uncertainty": max(0.02, 0.2 / (1 + len(prior))),
                "lexical_overlap_count": overlap,
                "empirical_outcomes": len(prior),
                "empirical_success_rate": empirical if prior else None,
            })
        decision = self.dcml.advanced.counterfactual_decide(scored)
        decision_id = decision["id"]
        chosen = decision["chosen_strategy"]
        evidence_id = self.store.add_evidence(
            session_id,
            "dcml_native_tool_choice",
            {
                "decision_id": decision_id,
                "selected_tool": chosen,
                "objective_sha256": hashlib.sha256(objective.encode()).hexdigest(),
                "candidate_names": sorted(names),
                "mission_id": (context or {}).get("mission_id"),
                "wing": (context or {}).get("wing"),
                "outcome_verified": False,
            },
            status="OBSERVED_LOCAL",
        )
        state = self.inspect_state()
        state.current_context = context or {}
        state.working_memory = [objective]
        state.capability_history.append("native_dcml_tool_choice")
        state.revision += 1
        self._save_state(state)
        self.store.event("dcml.tool_choice", {
            "decision_id": decision_id, "session_id": session_id,
            "selected_tool": chosen, "evidence_id": evidence_id,
            "state_revision": state.revision,
        })
        return {
            "schema": "kindred.brainstem.native-tool-choice.v1",
            "model_identity": self.state_id,
            "session_id": session_id,
            "decision_id": decision_id,
            "selected_tool": chosen,
            "choice_evidence_id": evidence_id,
            "state_revision": state.revision,
            "decision_policy": "dcml_counterfactual_utility_with_observed_feedback",
            "tool_candidates": len(scored),
            "scored_candidates": decision["candidates"],
            "outcome_verified": False,
            "external_model_used": False,
            "language_generation_performed": False,
            "external_action_executed": False,
        }

    def observe_native_tool_outcome(
        self,
        session_id: str,
        decision_id: str,
        selected_tool: str,
        observed_success: bool,
        provider_result_sha256: str,
        continuum_evidence_sha256: str,
        autonomy_audit_sha256: str,
    ) -> dict[str, Any]:
        """Record a gateway/Continuum-attested read outcome for future policy.

        The observation asserts *tool execution succeeded/failed*, not that
        an external customer outcome, prediction, or counterfactual was true.
        """
        evidence_hashes = (
            provider_result_sha256, continuum_evidence_sha256,
            autonomy_audit_sha256,
        )
        if not all(
            isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value)
            for value in evidence_hashes
        ) or not isinstance(observed_success, bool):
            raise ValueError("observed outcome requires three verifiable hashes")
        if not isinstance(decision_id, str) or not isinstance(selected_tool, str):
            raise ValueError("decision ID and selected tool required")
        decision_rows = self.store.query(
            "SELECT status,payload FROM counterfactual_decisions WHERE id=?",
            (decision_id,),
        )
        if not decision_rows:
            raise KeyError(decision_id)
        decision = decision_rows[0]
        payload = json.loads(decision["payload"])
        if payload.get("chosen_strategy") != selected_tool:
            raise ValueError("observed tool differs from BRAINSTEM's selection")
        choices = self.store.query(
            """SELECT id,content FROM evidence
               WHERE session_id=? AND kind='dcml_native_tool_choice'""",
            (session_id,),
        )
        choice = next((
            json.loads(item["content"]) for item in choices
            if json.loads(item["content"]).get("decision_id") == decision_id
        ), None)
        if choice is None or choice["selected_tool"] != selected_tool:
            raise ValueError("tool decision is not owned by this native session")
        earlier = self.store.query(
            """SELECT id,content FROM evidence
               WHERE session_id=? AND kind='dcml_native_tool_outcome'""",
            (session_id,),
        )
        for row in earlier:
            old = json.loads(row["content"])
            if old.get("decision_id") != decision_id:
                continue
            if (
                old.get("selected_tool") == selected_tool
                and old.get("observed_success") is observed_success
                and [old.get("provider_result_sha256"),
                     old.get("continuum_evidence_sha256"),
                     old.get("autonomy_audit_sha256")] == list(evidence_hashes)
            ):
                return {
                    "schema": "kindred.brainstem.native-tool-outcome.v1",
                    "decision_id": decision_id,
                    "outcome_evidence_id": row["id"],
                    "already_recorded": True,
                    "outcome_status": "observed_provider_execution",
                    "adaptive_policy_updated": True,
                }
            raise ValueError("conflicting tool outcome already exists")
        if decision["status"] != "AVAILABLE":
            raise ValueError("tool decision has already been evaluated")
        evaluation = self.dcml.advanced.observe_counterfactual(
            decision_id, float(observed_success), {}
        )
        evidence_id = self.store.add_evidence(
            session_id, "dcml_native_tool_outcome", {
                "decision_id": decision_id,
                "selected_tool": selected_tool,
                "observed_success": observed_success,
                "provider_result_sha256": provider_result_sha256,
                "continuum_evidence_sha256": continuum_evidence_sha256,
                "autonomy_audit_sha256": autonomy_audit_sha256,
                "counterfactual_observation_id": evaluation["id"],
                "alternative_outcomes_observed": False,
                "customer_success_verified": False,
            },
            status="OBSERVED_LOCAL",
        )
        state = self.inspect_state()
        state.capability_history.append("native_dcml_tool_outcome_observed")
        state.revision += 1
        self._save_state(state)
        self.store.event("dcml.tool_outcome_observed", {
            "decision_id": decision_id, "session_id": session_id,
            "evidence_id": evidence_id, "observed_success": observed_success,
            "state_revision": state.revision,
        })
        return {
            "schema": "kindred.brainstem.native-tool-outcome.v1",
            "model_identity": self.state_id,
            "decision_id": decision_id,
            "selected_tool": selected_tool,
            "observed_success": observed_success,
            "outcome_evidence_id": evidence_id,
            "state_revision": state.revision,
            "counterfactual_observation_id": evaluation["id"],
            "outcome_status": "observed_provider_execution",
            "adaptive_policy_updated": True,
            "model_weights_trained": False,
            "independent_customer_outcome_verified": False,
            "already_recorded": False,
        }

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

    def _transition_learning(
        self,
        learning_id: str,
        target: LearningStatus,
        evaluation: dict[str, Any] | None = None,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        rows = self.learning(learning_id)
        if not rows:
            raise KeyError(learning_id)
        current = LearningStatus(rows[0]["status"])
        if target not in _ALLOWED_TRANSITIONS.get(current, set()):
            raise ValueError(f"Invalid learning transition {current} -> {target}")
        self.store.execute(
            "UPDATE learning_proposals SET status=?, evaluation=COALESCE(?,evaluation), approval_id=COALESCE(?,approval_id), revision=revision+1, updated_at=? WHERE id=?",
            (
                target,
                json.dumps(evaluation) if evaluation else None,
                approval_id,
                now(),
                learning_id,
            ),
        )
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

    def approve_learning(self, learning_id: str, founder: str) -> dict[str, Any]:
        if founder != FOUNDER:
            raise PermissionError("Founder approval required")
        approval_id = _id("KAPR")
        self.store.execute(
            "INSERT INTO approvals VALUES(?,?,?,?,?)",
            (
                approval_id,
                f"promote_learning:{learning_id}",
                "APPROVED",
                founder,
                now(),
            ),
        )
        return self._transition_learning(
            learning_id, LearningStatus.APPROVED, approval_id=approval_id
        )

    def reject_learning(self, learning_id: str, founder: str) -> dict[str, Any]:
        if founder != FOUNDER:
            raise PermissionError("Founder authority required")
        rows = self.learning(learning_id)
        if not rows:
            raise KeyError(learning_id)
        current = LearningStatus(rows[0]["status"])
        if LearningStatus.REJECTED not in _ALLOWED_TRANSITIONS.get(current, set()):
            raise ValueError(f"Cannot reject from {current}")
        return self._transition_learning(learning_id, LearningStatus.REJECTED)

    def promote_learning(self, learning_id: str) -> dict[str, Any]:
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
                    strategy.get("description", "Founder-approved learned strategy"),
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
        return row

    def activate_learning(self, learning_id: str) -> dict[str, Any]:
        row = self._transition_learning(learning_id, LearningStatus.ACTIVE)
        self.store.execute(
            "UPDATE strategies SET status='ACTIVE' WHERE learning_id=?", (learning_id,)
        )
        self.store.execute(
            "UPDATE memory SET status='ACTIVE' WHERE evidence_id=?", (learning_id,)
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
        return row

    def rollback_learning(self, learning_id: str) -> dict[str, Any]:
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

    def rollback(self, checkpoint_id: str) -> CognitiveState:
        rows = self.store.query(
            "SELECT snapshot FROM model_checkpoints WHERE id=?", (checkpoint_id,)
        )
        if not rows:
            raise KeyError(checkpoint_id)
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

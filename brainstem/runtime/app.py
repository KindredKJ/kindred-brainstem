"""Typed local HTTP API for the BRAINSTEM runtime."""

from __future__ import annotations

import asyncio
import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from brainstem.runtime.paths import global_state_dir
from brainstem.runtime.service import RuntimeService
from brainstem.runtime.store import StateStore
from brainstem.runtime.operators import WorkforceOperatorSupervisor, ContractViolationError


class SessionRequest(BaseModel):
    model: str | None = None
    repository: str | None = None


class ChatRequest(BaseModel):
    session_id: str
    message: str


class SwitchRequest(BaseModel):
    model: str


class LearningDecision(BaseModel):
    founder: str


class LearningEvaluation(BaseModel):
    score: float
    evidence: list[str]


class DCMLCycleRequest(BaseModel):
    session_id: str
    message: str


class WorkforceDispatchRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)
    contract_id: str = Field(min_length=6, max_length=72)
    payload: dict[str, Any] = Field(default_factory=dict)
    lease_seconds: int = Field(default=60, ge=5, le=3600)
    depends_on: list[str] = Field(default_factory=list, max_length=16)


class WorkforceContractRequest(BaseModel):
    contract_id: str
    capability: str
    version: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    max_lease_seconds: int = Field(default=60, ge=5, le=3600)
    max_retries: int = Field(default=2, ge=0, le=8)
    require_live_signal_lane: bool = True
    verification_tier: str = "signal_lane"


class WorkforceLeaseRenewalRequest(BaseModel):
    seconds: int = Field(default=15, ge=5, le=60)


class WorkforceObservationRequest(BaseModel):
    source: str
    worker_id: str
    kind: str
    status: str
    details: dict[str, Any] = Field(default_factory=dict)


def build_app(
    database: Path | None = None, service: RuntimeService | None = None
) -> FastAPI:
    db = database or Path(
        os.getenv("KINDRED_STATE_DB", global_state_dir() / "brainstem.db")
    )
    runtime = service or RuntimeService(StateStore(db))
    awareness = runtime.awareness
    orchestrator = runtime.orchestrator
    supervisor = WorkforceOperatorSupervisor(runtime.store, orchestrator)

    async def _continuous_awareness() -> None:
        while True:
            await asyncio.to_thread(awareness.sync_emit)
            await asyncio.sleep(15)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = None
        operator_task = asyncio.create_task(supervisor.run_forever())
        if os.getenv("KINDRED_EMIT_CORE_URL") and os.getenv("KINDRED_INTERNAL_SERVICE_KEY"):
            task = asyncio.create_task(_continuous_awareness())
        try:
            yield
        finally:
            supervisor.stop()
            operator_task.cancel()
            try:
                await operator_task
            except asyncio.CancelledError:
                pass
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app = FastAPI(
        title="Kindred BRAINSTEM Runtime",
        version="0.1.0-alpha",
        lifespan=lifespan,
    )
    app.state.runtime = runtime
    app.state.operational_awareness = awareness
    app.state.workforce_orchestrator = orchestrator
    app.state.workforce_supervisor = supervisor

    def _require_awareness_key(
        x_brainstem_awareness_key: str | None = Header(default=None),
    ) -> None:
        expected = os.getenv("BRAINSTEM_AWARENESS_KEY", "")
        if not expected or not x_brainstem_awareness_key or not hmac.compare_digest(expected, x_brainstem_awareness_key):
            raise HTTPException(401, "BRAINSTEM awareness key required")

    @app.get("/awareness")
    def awareness_state() -> dict[str, Any]:
        return awareness.overview()

    @app.get("/awareness/workers")
    def workforce_state() -> dict[str, Any]:
        return awareness.overview()

    @app.post("/awareness/sync")
    def awareness_sync(
        x_brainstem_awareness_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_awareness_key(x_brainstem_awareness_key)
        return awareness.sync_emit()

    @app.post("/awareness/workers/observe")
    def observe_worker(
        request: WorkforceObservationRequest,
        x_brainstem_awareness_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_awareness_key(x_brainstem_awareness_key)
        try:
            return awareness.observe(
                request.source, request.worker_id,
                request.kind, request.status, request.details,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/contracts")
    @app.get("/orchestration/contracts")
    def workforce_contracts(
        x_brainstem_awareness_key: str | None = Header(default=None),
    ) -> list[dict[str, Any]]:
        _require_awareness_key(x_brainstem_awareness_key)
        return orchestrator.contracts.list_contracts()

    @app.post("/contracts", status_code=201)
    @app.post("/orchestration/contracts", status_code=201)
    def register_workforce_contract(
        request: WorkforceContractRequest,
        x_brainstem_awareness_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_awareness_key(x_brainstem_awareness_key)
        if request.capability not in {"runtime.snapshot", "signal.deliver"}:
            raise HTTPException(422, "EMIT does not implement this execution capability")
        try:
            return orchestrator.contracts.register_contract(**request.model_dump())
        except ContractViolationError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/contracts/{contract_id}")
    def get_workforce_contract(
        contract_id: str,
        x_brainstem_awareness_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_awareness_key(x_brainstem_awareness_key)
        try:
            return orchestrator.contracts.contract(contract_id, require_active=False)
        except ContractViolationError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.delete("/contracts/{contract_id}")
    def retire_workforce_contract(
        contract_id: str,
        x_brainstem_awareness_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_awareness_key(x_brainstem_awareness_key)
        try:
            return orchestrator.contracts.deactivate_contract(contract_id)
        except ContractViolationError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/orchestration/dispatch")
    def workforce_dispatch(
        request: WorkforceDispatchRequest,
        x_brainstem_awareness_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_awareness_key(x_brainstem_awareness_key)
        from brainstem.runtime.workforce_orchestration import OrchestrationError
        try:
            return orchestrator.dispatch(**request.model_dump())
        except OrchestrationError as exc:
            raise HTTPException(exc.status_code, exc.detail) from exc

    @app.get("/orchestration/tasks/{task_id}")
    def workforce_task(
        task_id: str,
        x_brainstem_awareness_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_awareness_key(x_brainstem_awareness_key)
        from brainstem.runtime.workforce_orchestration import OrchestrationError
        try:
            return orchestrator.task(task_id)
        except OrchestrationError as exc:
            raise HTTPException(exc.status_code, exc.detail) from exc

    @app.post("/orchestration/tasks/{task_id}/renew")
    def renew_workforce_task(
        task_id: str,
        request: WorkforceLeaseRenewalRequest,
        x_brainstem_awareness_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_awareness_key(x_brainstem_awareness_key)
        from brainstem.runtime.workforce_orchestration import OrchestrationError
        try:
            return orchestrator.renew_lease(task_id, request.seconds)
        except OrchestrationError as exc:
            raise HTTPException(exc.status_code, exc.detail) from exc

    @app.get("/orchestration/cognitive-summary")
    def workforce_cognitive_summary(
        limit: int = 10,
        x_brainstem_awareness_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_awareness_key(x_brainstem_awareness_key)
        return orchestrator.summary(limit)

    @app.get("/orchestration/operator-events")
    def workforce_operator_events(
        limit: int = 50,
        x_brainstem_awareness_key: str | None = Header(default=None),
    ) -> list[dict[str, Any]]:
        _require_awareness_key(x_brainstem_awareness_key)
        with runtime.store.connect() as dbh:
            return [dict(row) for row in dbh.execute(
                "SELECT * FROM operator_audit_log ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            )]

    @app.get("/dcml/status")
    def dcml_status() -> dict[str, Any]:
        return runtime.model.dcml.status()

    @app.post("/dcml/cycle")
    def dcml_cycle(request: DCMLCycleRequest) -> dict[str, Any]:
        return runtime.chat(request.session_id, request.message)

    @app.get("/dcml/experiences")
    def dcml_experiences() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("experiences_v2")

    @app.get("/dcml/evaluations")
    def dcml_evaluations() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("outcome_evaluations")

    @app.get("/dcml/learning")
    def dcml_learning() -> list[dict[str, Any]]:
        return runtime.model.learning()

    @app.get("/dcml/datasets")
    def dcml_datasets() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("datasets")

    @app.get("/dcml/training")
    def dcml_training() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("training_runs")

    @app.get("/dcml/checkpoints")
    def dcml_checkpoints() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("policy_parameters")

    @app.get("/dcml/benchmarks")
    def dcml_benchmarks() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("benchmark_runs")

    @app.get("/dcml/calibration")
    def dcml_calibration() -> dict[str, Any]:
        return runtime.model.dcml.calibrate()

    @app.post("/dcml/consolidation")
    def dcml_consolidation() -> dict[str, str]:
        return {"consolidation_id": runtime.model.dcml.consolidate()}

    @app.get("/dcml/skills")
    def dcml_skills() -> list[dict[str, Any]]:
        return runtime.model.skills()

    @app.get("/dcml/lineage")
    def dcml_lineage() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("lineage_records")

    @app.get("/strata/ports/health")
    def strata_ports_health() -> dict[str, Any]:
        return runtime.strata.status()

    @app.get("/strata/ports/audit")
    def strata_ports_audit() -> list[dict[str, Any]]:
        return runtime.store.query(
            "SELECT sequence,request_id,tenant_id,prior_state,new_state,payload_hash,created_at FROM strata_boundary_events ORDER BY sequence"
        )

    @app.get("/strata/ports/trace/{request_id}")
    def strata_ports_trace(request_id: str) -> dict[str, Any]:
        requests = runtime.store.query(
            "SELECT * FROM strata_boundary_requests WHERE request_id=?", (request_id,)
        )
        if not requests:
            raise HTTPException(404, "Boundary request not found")
        return {
            "request": requests[0],
            "events": runtime.store.query(
                "SELECT * FROM strata_boundary_events WHERE request_id=? ORDER BY sequence",
                (request_id,),
            ),
        }

    @app.get("/dcml/concepts")
    def dcml_concepts() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("concepts")

    @app.get("/dcml/transfers")
    def dcml_transfers() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("transfer_evaluations")

    @app.get("/dcml/causal")
    def dcml_causal() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("causal_hypotheses")

    @app.get("/dcml/counterfactuals")
    def dcml_counterfactuals() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("counterfactual_decisions")

    @app.get("/dcml/routing")
    def dcml_routing() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("routing_decisions")

    @app.get("/dcml/metacognition")
    def dcml_metacognition() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("metacognitive_reviews")

    @app.get("/dcml/missions")
    def dcml_missions() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("missions_v2")

    @app.get("/dcml/temporal-credit")
    def dcml_temporal_credit() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("temporal_credit")

    @app.get("/dcml/advanced-benchmarks")
    def dcml_advanced_benchmarks() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("advanced_benchmark_runs")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return runtime.health()

    @app.get("/identity")
    def identity() -> dict[str, str]:
        return runtime.identity()

    @app.get("/models")
    def models() -> list[dict[str, Any]]:
        return runtime.models()

    @app.post("/sessions")
    def create_session(request: SessionRequest) -> dict[str, Any]:
        try:
            return runtime.create_session(request.model, request.repository)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.get("/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, Any]:
        try:
            session = runtime.store.session(session_id)
            return {**session, "history": runtime.store.history(session_id)}
        except KeyError as exc:
            raise HTTPException(404, "Session not found") from exc

    @app.post("/sessions/{session_id}/model")
    def switch(session_id: str, request: SwitchRequest) -> dict[str, Any]:
        try:
            return runtime.switch(session_id, request.model)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/chat")
    def chat(request: ChatRequest) -> dict[str, Any]:
        try:
            return runtime.chat(request.session_id, request.message)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.get("/events")
    def events() -> list[dict[str, Any]]:
        with runtime.store.connect() as dbh:
            return [
                dict(row)
                for row in dbh.execute("SELECT * FROM events ORDER BY created_at")
            ]

    @app.get("/evidence")
    def evidence() -> list[dict[str, Any]]:
        with runtime.store.connect() as dbh:
            return [
                dict(row)
                for row in dbh.execute("SELECT * FROM evidence ORDER BY created_at")
            ]

    @app.get("/learning")
    def learning() -> list[dict[str, Any]]:
        return runtime.model.learning()

    @app.get("/learning/{learning_id}")
    def learning_item(learning_id: str) -> dict[str, Any]:
        rows = runtime.model.learning(learning_id)
        if not rows:
            raise HTTPException(404, "Learning proposal not found")
        return rows[0]

    @app.post("/learning/{learning_id}/evaluate")
    def learning_evaluate(
        learning_id: str, request: LearningEvaluation
    ) -> dict[str, Any]:
        try:
            return runtime.model.evaluate_learning(
                learning_id, request.score, request.evidence
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/learning/{learning_id}/promote")
    def learning_promote(learning_id: str) -> dict[str, Any]:
        try:
            return runtime.model.promote_learning(learning_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/learning/{learning_id}/activate")
    def learning_activate(learning_id: str) -> dict[str, Any]:
        try:
            return runtime.model.activate_learning(learning_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/learning/{learning_id}/rollback")
    def learning_rollback(learning_id: str) -> dict[str, Any]:
        try:
            return runtime.model.rollback_learning(learning_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/learning/{learning_id}/approve")
    def learning_approve(learning_id: str, request: LearningDecision) -> dict[str, Any]:
        try:
            return runtime.model.approve_learning(learning_id, request.founder)
        except (KeyError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @app.post("/learning/{learning_id}/reject")
    def learning_reject(learning_id: str, request: LearningDecision) -> dict[str, Any]:
        try:
            return runtime.model.reject_learning(learning_id, request.founder)
        except (KeyError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @app.get("/memory")
    def memory() -> list[dict[str, Any]]:
        with runtime.store.connect() as dbh:
            return [
                dict(row)
                for row in dbh.execute("SELECT * FROM memory ORDER BY created_at")
            ]

    @app.get("/world")
    def world() -> dict[str, Any]:
        return runtime.model.world()

    @app.get("/cognitive")
    def cognitive() -> dict[str, Any]:
        return {
            "status": "AVAILABLE",
            "trained_weights": "NOT_TRAINED",
            "state": runtime.model.inspect_state().model_dump(),
        }

    @app.get("/beliefs")
    def beliefs() -> list[dict[str, Any]]:
        return runtime.model.beliefs()

    @app.get("/strategies")
    def strategies() -> list[dict[str, Any]]:
        return runtime.model.strategies()

    @app.get("/skills")
    def skills() -> list[dict[str, Any]]:
        return runtime.model.skills()

    @app.get("/telemetry")
    def telemetry() -> list[dict[str, Any]]:
        return runtime.model.telemetry()

    @app.post("/cognitive/checkpoint")
    def checkpoint() -> dict[str, str]:
        return {"checkpoint_id": runtime.model.checkpoint()}

    @app.post("/cognitive/rollback/{checkpoint_id}")
    def rollback(checkpoint_id: str) -> dict[str, Any]:
        try:
            return runtime.model.rollback(checkpoint_id).model_dump()
        except KeyError as exc:
            raise HTTPException(404, "Checkpoint not found") from exc

    @app.get("/memory/consolidations")
    def memory_consolidations() -> list[dict[str, Any]]:
        return runtime.model.dcml.list_records("consolidation_runs")

    @app.get("/memory/conflicts")
    def memory_conflicts() -> list[dict[str, Any]]:
        return runtime.model.store.query(
            "SELECT * FROM beliefs WHERE status='CONFLICTED'"
        )

    @app.get("/memory/{memory_id}/provenance")
    def memory_provenance(memory_id: str) -> dict[str, Any]:
        rows = runtime.model.store.query(
            "SELECT * FROM memory WHERE id=?", (memory_id,)
        )
        if not rows:
            raise HTTPException(404, "Memory not found")
        return rows[0]

    @app.get("/missions")
    def missions() -> dict[str, Any]:
        return {"status": "NOT_IMPLEMENTED", "items": []}

    @app.get("/approvals")
    def approvals() -> list[dict[str, Any]]:
        with runtime.store.connect() as dbh:
            return [
                dict(row)
                for row in dbh.execute("SELECT * FROM approvals ORDER BY created_at")
            ]

    return app


app = build_app()

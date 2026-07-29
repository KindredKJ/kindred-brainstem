"""Typed local HTTP API for the BRAINSTEM runtime."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from brainstem.runtime.paths import global_state_dir
from brainstem.runtime.service import RuntimeService
from brainstem.runtime.store import StateStore


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


def build_app(
    database: Path | None = None, service: RuntimeService | None = None
) -> FastAPI:
    db = database or Path(
        os.getenv("KINDRED_STATE_DB", global_state_dir() / "brainstem.db")
    )
    runtime = service or RuntimeService(StateStore(db))
    app = FastAPI(title="Kindred BRAINSTEM Runtime", version="0.1.0-alpha")
    app.state.runtime = runtime

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

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
        with runtime.store.connect() as dbh:
            return [
                dict(row)
                for row in dbh.execute("SELECT * FROM learning ORDER BY created_at")
            ]

    @app.get("/memory")
    def memory() -> list[dict[str, Any]]:
        with runtime.store.connect() as dbh:
            return [
                dict(row)
                for row in dbh.execute("SELECT * FROM memory ORDER BY created_at")
            ]

    @app.get("/world")
    def world() -> dict[str, Any]:
        return {"status": "NOT_IMPLEMENTED", "version": None, "nodes": []}

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

"""Serving orchestration that delegates all cognitive work to BrainstemModel."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from typing import Any

from brainstem.adapters.models import (
    CodexAdapter,
    HCaratAdapter,
    ModelAdapter,
    OpenAICompatibleAdapter,
)
from brainstem.model import BrainstemModel
from brainstem.runtime.store import StateStore
from brainstem.strata.gateway import PortZeroGateway

FOUNDER = "Kindred Jermaine Cox"


class SubmissionInProgress(RuntimeError):
    """A matching request owns the durable processing claim."""


class RuntimeService:
    def __init__(
        self, store: StateStore, adapters: dict[str, ModelAdapter] | None = None
    ) -> None:
        self.store = store
        self.adapters = adapters or {
            "h-carat": HCaratAdapter(),
            "configured": OpenAICompatibleAdapter(),
            "codex": CodexAdapter(),
        }
        self.model = BrainstemModel(store, self.adapters)
        self.strata = PortZeroGateway(store, self.model.dcml.authority)

    def health(self) -> dict[str, Any]:
        database = "HEALTHY"
        try:
            self.store.counts()
        except (OSError, sqlite3.Error):
            database = "UNAVAILABLE"
        models = {}
        for name, adapter in self.adapters.items():
            health = adapter.health()
            models[name] = {"status": health.status, "detail": health.detail}
        model_available = any(item["status"] == "HEALTHY" for item in models.values())
        status = "HEALTHY" if database == "HEALTHY" and model_available else "DEGRADED"
        return {
            "status": status,
            "database": database,
            "models": models,
            "default_model": "h-carat",
            "identity": "AVAILABLE",
        }

    def identity(self) -> dict[str, str]:
        return {
            "product": "Kindred BRAINSTEM",
            "founder": FOUNDER,
            "organization": "Kindred Labs",
            "license": "LicenseRef-Kindred-Proprietary",
            "attribution": f"Originated by {FOUNDER} & Kindred Labs",
        }

    def models(self) -> list[dict[str, Any]]:
        result = []
        for name, adapter in self.adapters.items():
            health = adapter.health()
            result.append(
                {
                    "id": name,
                    "identity": adapter.identity,
                    "status": health.status,
                    "detail": health.detail,
                    "capabilities": sorted(adapter.capabilities()),
                    "default": name == "h-carat",
                }
            )
        return result

    def create_session(
        self, model: str | None = None, repository: str | None = None
    ) -> dict[str, Any]:
        selected = model or "h-carat"
        if selected == "auto":
            if not any(
                adapter.health().status == "HEALTHY"
                for adapter in self.adapters.values()
            ):
                raise RuntimeError(
                    "No healthy model route is available; no fallback attempted"
                )
            return self.store.create_session(selected, repository)
        if selected not in self.adapters:
            raise KeyError(f"Unknown model: {selected}")
        health = self.adapters[selected].health()
        if health.status != "HEALTHY":
            self.store.event(
                "model.attachment_blocked", {"model": selected, "status": health.status}
            )
            raise RuntimeError(f"{selected} {health.status}: {health.detail}")
        return self.store.create_session(selected, repository)

    def switch(self, session_id: str, model: str) -> dict[str, Any]:
        if model != "auto" and model not in self.adapters:
            raise KeyError(f"Unknown model: {model}")
        self.store.set_model(session_id, model)
        return self.store.session(session_id)

    def chat(
        self, session_id: str, text: str, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        key = idempotency_key or f"internal-{uuid.uuid4().hex}"
        if len(key) < 16 or len(key) > 200:
            raise ValueError("idempotency key must contain 16 to 200 characters")
        request_hash = hashlib.sha256(
            json.dumps(
                {"session_id": session_id, "message": text},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        status, prior = self.store.claim_submission(
            "chat", key, session_id, request_hash
        )
        if status == "COMPLETED":
            if prior is None:
                raise RuntimeError("Completed submission is missing its response")
            return prior
        if status == "FAILED":
            failed = self.store.submission("chat", key)
            raise RuntimeError(
                f"Prior idempotent submission failed: {failed['error'] if failed else 'unknown'}"
            )
        if status == "PROCESSING":
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                current = self.store.submission("chat", key)
                if current and current["status"] == "COMPLETED":
                    return json.loads(current["response"])
                if current and current["status"] == "FAILED":
                    raise RuntimeError(
                        f"Prior idempotent submission failed: {current['error']}"
                    )
                time.sleep(0.01)
            raise SubmissionInProgress("Matching submission is still processing")
        model_name: str | None = None
        try:
            session = self.store.session(session_id)
            model_name = session["model"]
            self.store.add_message(session_id, "user", text)
            result = self.model.cognitive_cycle(
                session_id,
                text,
                model_name,
                {"repository": session.get("repository"), "session_id": session_id},
            )
            self.store.add_message(session_id, "assistant", result.response, model_name)
            response = {
                **result.model_dump(),
                "model": model_name,
                "learning_status": (
                    "PROPOSED" if result.learning_proposal_id else None
                ),
            }
            self.store.complete_submission("chat", key, response)
            return response
        except Exception as exc:
            self.store.event(
                "model.failed",
                {
                    "session_id": session_id,
                    "instrument": model_name,
                    "error_type": type(exc).__name__,
                },
            )
            self.store.fail_submission("chat", key, type(exc).__name__)
            if isinstance(exc, KeyError):
                raise
            raise RuntimeError(
                f"{model_name} failed; no fallback attempted: {exc}"
            ) from exc

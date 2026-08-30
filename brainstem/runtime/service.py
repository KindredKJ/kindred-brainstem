"""Serving orchestration that delegates all cognitive work to BrainstemModel."""

from __future__ import annotations

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
        except Exception:
            database = "UNAVAILABLE"
        models = {}
        for name, adapter in self.adapters.items():
            try:
                health = adapter.health()
            except Exception as exc:
                models[name] = {"status": "UNAVAILABLE", "detail": f"health probe failed: {type(exc).__name__}"}
                continue
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
        self.store.session(session_id)
        if model != "auto" and model not in self.adapters:
            raise KeyError(f"Unknown model: {model}")
        if model != "auto" and self.adapters[model].health().status != "HEALTHY":
            raise RuntimeError(f"Model {model} is not healthy")
        self.store.set_model(session_id, model)
        return self.store.session(session_id)

    def chat(self, session_id: str, text: str) -> dict[str, Any]:
        session = self.store.session(session_id)
        model_name = session["model"]
        self.store.add_message(session_id, "user", text)
        try:
            result = self.model.cognitive_cycle(
                session_id,
                text,
                model_name,
                {"repository": session.get("repository"), "session_id": session_id},
            )
        except Exception as exc:
            self.store.event(
                "model.failed",
                {
                    "session_id": session_id,
                    "instrument": model_name,
                    "error_type": type(exc).__name__,
                },
            )
            raise RuntimeError(
                f"{model_name} failed; no fallback attempted: {exc}"
            ) from exc
        self.store.add_message(session_id, "assistant", result.response, model_name)
        return {
            **result.model_dump(),
            "model": model_name,
            "learning_status": "PROPOSED" if result.learning_proposal_id else None,
        }

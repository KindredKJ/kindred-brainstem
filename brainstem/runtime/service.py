"""BRAINSTEM orchestration service: policy and state remain outside model adapters."""

from __future__ import annotations

from typing import Any

from brainstem.adapters.models import (
    CodexAdapter,
    HCaratAdapter,
    ModelAdapter,
    OpenAICompatibleAdapter,
)
from brainstem.runtime.store import StateStore

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

    def health(self) -> dict[str, Any]:
        database = "HEALTHY"
        try:
            self.store.counts()
        except Exception:
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
        if model not in self.adapters:
            raise KeyError(f"Unknown model: {model}")
        self.store.set_model(session_id, model)
        return self.store.session(session_id)

    def chat(self, session_id: str, text: str) -> dict[str, Any]:
        session = self.store.session(session_id)
        model_name = session["model"]
        adapter = self.adapters[model_name]
        health = adapter.health()
        self.store.add_message(session_id, "user", text)
        if health.status != "HEALTHY":
            self.store.event(
                "model.failed",
                {
                    "session_id": session_id,
                    "model": model_name,
                    "status": health.status,
                    "detail": health.detail,
                },
            )
            raise RuntimeError(
                f"{model_name} {health.status}: {health.detail}; no fallback attempted"
            )
        messages = [
            {"role": item["role"], "content": item["content"]}
            for item in self.store.history(session_id)
        ]
        generation = adapter.generate(messages)
        self.store.add_message(
            session_id, "assistant", generation.text, generation.model
        )
        evidence_id = self.store.add_evidence(
            session_id,
            "model_response",
            {"model": generation.model, "usage": generation.usage},
        )
        learning_id = self.store.propose_learning(
            "model_performance",
            f"Evaluate {generation.model} response outcome.",
            evidence_id,
        )
        return {
            "session_id": session_id,
            "model": generation.model,
            "response": generation.text,
            "usage": generation.usage,
            "evidence_id": evidence_id,
            "learning_id": learning_id,
            "learning_status": "PROPOSED",
        }

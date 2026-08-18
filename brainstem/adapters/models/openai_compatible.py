"""Adapter for explicitly configured OpenAI-compatible local/provider endpoints."""

from __future__ import annotations

import json
import os
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .base import Generation, ModelAdapter, ModelHealth


class OpenAICompatibleAdapter(ModelAdapter):
    identity = "openai-compatible"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        resolved_url: str = base_url or os.getenv("KINDRED_MODEL_BASE_URL") or ""
        self.base_url: str = resolved_url.rstrip("/")
        if self.base_url and urlparse(self.base_url).scheme not in {"http", "https"}:
            raise ValueError("Model endpoint must use HTTP or HTTPS")
        self.model: str = model or os.getenv("KINDRED_MODEL_NAME") or ""
        self.api_key = api_key or os.getenv("KINDRED_MODEL_API_KEY")

    def capabilities(self) -> set[str]:
        return {"generate", "chat"} if self.base_url and self.model else set()

    def _request(
        self, path: str, payload: dict | None = None, timeout: float = 2
    ) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(  # noqa: S310 -- constructor restricts endpoint schemes
            f"{self.base_url}{path}",
            headers=headers,
            data=json.dumps(payload).encode() if payload else None,
            method="POST" if payload else "GET",
        )
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read())

    def health(self) -> ModelHealth:
        if not self.base_url or not self.model:
            return ModelHealth(
                "NOT_CONFIGURED", "Set KINDRED_MODEL_BASE_URL and KINDRED_MODEL_NAME."
            )
        try:
            self._request("/models")
            return ModelHealth(
                "HEALTHY", "Configured endpoint answered the models probe."
            )
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            return ModelHealth(
                "UNAVAILABLE", f"Endpoint health probe failed: {type(exc).__name__}"
            )

    def generate(self, messages: list[dict[str, str]]) -> Generation:
        health = self.health()
        if health.status != "HEALTHY":
            raise RuntimeError(f"{health.status}: {health.detail}")
        result = self._request(
            "/chat/completions",
            {"model": self.model, "messages": messages, "stream": False},
            timeout=120,
        )
        text = result["choices"][0]["message"]["content"]
        usage = {key: int(value) for key, value in result.get("usage", {}).items()}
        return Generation(text=text, model=self.model, usage=usage)

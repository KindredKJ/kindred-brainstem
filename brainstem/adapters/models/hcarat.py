"""H^ adapter enabled only by explicit HCarat configuration and a live probe."""

from __future__ import annotations

import os

from .base import ModelHealth
from .openai_compatible import OpenAICompatibleAdapter


class HCaratAdapter(OpenAICompatibleAdapter):
    identity = "h-carat"

    def __init__(self) -> None:
        super().__init__(
            base_url=os.getenv("KINDRED_HCARAT_BASE_URL"),
            model=os.getenv("KINDRED_HCARAT_MODEL"),
            api_key=os.getenv("KINDRED_HCARAT_API_KEY"),
        )

    def health(self) -> ModelHealth:
        health = super().health()
        if health.status == "NOT_CONFIGURED":
            return ModelHealth(
                "NOT_CONFIGURED",
                "Set KINDRED_HCARAT_BASE_URL and KINDRED_HCARAT_MODEL after validating the H^ runtime and license.",
            )
        return health

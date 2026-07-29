"""Provider-independent model adapter contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ModelHealth:
    status: str
    detail: str


@dataclass(frozen=True)
class Generation:
    text: str
    model: str
    usage: dict[str, int]


class ModelAdapter(ABC):
    identity: str

    @abstractmethod
    def capabilities(self) -> set[str]: ...

    @abstractmethod
    def health(self) -> ModelHealth: ...

    @abstractmethod
    def generate(self, messages: list[dict[str, str]]) -> Generation: ...

    def stream(self, messages: list[dict[str, str]]) -> Iterable[str]:
        yield self.generate(messages).text

    def cancel(self) -> None:
        """Cancel an active provider operation when supported."""

    def usage(self) -> dict[str, int]:
        return {}

"""LLMGateway port — abstraction over LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    cached: bool = False


class LLMGateway(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse: ...

    @abstractmethod
    async def is_available(self, model: str) -> bool: ...

    @abstractmethod
    async def list_models(self) -> list[str]: ...

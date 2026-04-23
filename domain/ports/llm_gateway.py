"""LLMGateway port — abstraction over LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallResult:
    """A single tool call returned by the LLM."""

    id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    cached: bool = False
    cached_tokens: int = 0
    tool_calls: list[ToolCallResult] = field(default_factory=list)


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

    async def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Complete with tool-calling support. Default raises NotImplementedError."""
        raise NotImplementedError("This gateway does not support tool calling")

"""OllamaEngineDriver — wraps LiteLLMGateway + OllamaManager as an AgentEnginePort."""

from __future__ import annotations

import time

from domain.ports.agent_engine import (
    AgentEngineCapabilities,
    AgentEnginePort,
    AgentEngineResult,
)
from domain.ports.llm_gateway import LLMGateway
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.llm.ollama_manager import OllamaManager

_DEFAULT_MODEL = "qwen3:8b"


class OllamaEngineDriver(AgentEnginePort):
    """Agent engine backed by local Ollama via the existing LiteLLMGateway.

    Reuses cost tracking, model routing, and Ollama httpx from LiteLLMGateway.
    Always cost_usd=0 (local execution).
    """

    engine_type: AgentEngineType = AgentEngineType.OLLAMA

    def __init__(self, gateway: LLMGateway, ollama: OllamaManager) -> None:
        self._gateway = gateway
        self._ollama = ollama

    async def run_task(
        self,
        task: str,
        model: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> AgentEngineResult:
        resolved = model or _DEFAULT_MODEL
        if not resolved.startswith("ollama/"):
            resolved = f"ollama/{resolved}"

        start = time.monotonic()
        try:
            resp = await self._gateway.complete(
                messages=[{"role": "user", "content": task}],
                model=resolved,
            )
            duration = time.monotonic() - start
            return AgentEngineResult(
                engine=AgentEngineType.OLLAMA,
                success=True,
                output=resp.content,
                cost_usd=resp.cost_usd,
                duration_seconds=duration,
                model_used=resp.model,
            )
        except Exception as exc:
            duration = time.monotonic() - start
            return AgentEngineResult(
                engine=AgentEngineType.OLLAMA,
                success=False,
                output="",
                error=str(exc),
                duration_seconds=duration,
                model_used=resolved,
            )

    async def is_available(self) -> bool:
        return await self._ollama.is_running()

    def get_capabilities(self) -> AgentEngineCapabilities:
        return AgentEngineCapabilities(
            engine_type=AgentEngineType.OLLAMA,
            max_context_tokens=32_768,
            supports_sandbox=False,
            supports_parallel=False,
            supports_mcp=False,
            supports_streaming=False,
            cost_per_hour_usd=0.0,
        )

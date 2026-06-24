"""RouteToEngine-backed registry for Morphic Chat CLI engines."""

from __future__ import annotations

from typing import Protocol

from application.use_cases.route_to_engine import EngineStatus
from domain.ports.engine_registry import (
    EngineProfile,
    EngineRegistryPort,
    EngineRuntimeKind,
)
from domain.value_objects.agent_engine import AgentEngineType


class _RouteEngineStatusSource(Protocol):
    async def list_engines(self) -> list[EngineStatus]: ...

    async def get_engine(self, engine_type: AgentEngineType) -> EngineStatus | None: ...


class RouteEngineRegistry(EngineRegistryPort):
    """Expose existing route-to-engine availability as chat engine profiles."""

    _DISPLAY_NAMES: dict[AgentEngineType, str] = {
        AgentEngineType.ADK: "Google ADK",
        AgentEngineType.CLAUDE_CODE: "Claude Code",
        AgentEngineType.CODEX_CLI: "Codex CLI",
        AgentEngineType.GEMINI_CLI: "Gemini CLI",
        AgentEngineType.OLLAMA: "Ollama",
        AgentEngineType.OPENHANDS: "OpenHands",
    }
    _RUNTIME_KINDS: dict[AgentEngineType, EngineRuntimeKind] = {
        AgentEngineType.ADK: EngineRuntimeKind.SDK,
        AgentEngineType.CLAUDE_CODE: EngineRuntimeKind.EXTERNAL_CLI,
        AgentEngineType.CODEX_CLI: EngineRuntimeKind.EXTERNAL_CLI,
        AgentEngineType.GEMINI_CLI: EngineRuntimeKind.EXTERNAL_CLI,
        AgentEngineType.OLLAMA: EngineRuntimeKind.LOCAL_MODEL,
        AgentEngineType.OPENHANDS: EngineRuntimeKind.SANDBOX_RUNTIME,
    }
    _BASE_CAPABILITIES: dict[AgentEngineType, list[str]] = {
        AgentEngineType.ADK: ["workflow_orchestration"],
        AgentEngineType.CLAUDE_CODE: ["architecture_review", "workspace_editing"],
        AgentEngineType.CODEX_CLI: ["code_generation", "workspace_editing"],
        AgentEngineType.GEMINI_CLI: ["long_context", "planning"],
        AgentEngineType.OLLAMA: ["planning", "drafting"],
        AgentEngineType.OPENHANDS: ["sandbox_execution", "workspace_editing"],
    }
    _EDITING_ENGINES = {
        AgentEngineType.CLAUDE_CODE,
        AgentEngineType.CODEX_CLI,
        AgentEngineType.OPENHANDS,
    }
    _JSON_OUTPUT_ENGINES = {AgentEngineType.CODEX_CLI}

    def __init__(self, route_to_engine: _RouteEngineStatusSource) -> None:
        self._route_to_engine = route_to_engine

    async def list_engines(self) -> list[EngineProfile]:
        statuses = await self._route_to_engine.list_engines()
        return [self._profile_for(status) for status in statuses]

    async def get_engine(self, engine_id: str) -> EngineProfile | None:
        try:
            engine_type = AgentEngineType(engine_id)
        except ValueError:
            return None
        status = await self._route_to_engine.get_engine(engine_type)
        if status is None:
            return None
        return self._profile_for(status)

    def _profile_for(self, status: EngineStatus) -> EngineProfile:
        capabilities = list(self._BASE_CAPABILITIES.get(status.engine_type, []))
        if status.capabilities.supports_mcp:
            capabilities.append("mcp")
        if status.capabilities.supports_parallel:
            capabilities.append("parallel_execution")

        return EngineProfile(
            id=status.engine_type.value,
            display_name=self._DISPLAY_NAMES.get(
                status.engine_type, status.engine_type.value
            ),
            kind=self._RUNTIME_KINDS.get(
                status.engine_type, EngineRuntimeKind.EXTERNAL_CLI
            ),
            capabilities=capabilities,
            available=status.available,
            cost_profile=self._cost_profile_for(status),
            context_window=status.capabilities.max_context_tokens,
            supports_streaming=status.capabilities.supports_streaming,
            supports_editing=status.engine_type in self._EDITING_ENGINES,
            supports_sandbox=(
                status.capabilities.supports_sandbox
                or status.engine_type is AgentEngineType.OPENHANDS
            ),
            supports_json_output=status.engine_type in self._JSON_OUTPUT_ENGINES,
        )

    def _cost_profile_for(self, status: EngineStatus) -> str:
        if status.engine_type is AgentEngineType.OLLAMA:
            return "local"
        if status.capabilities.cost_per_hour_usd > 0:
            return "paid"
        return "provider"

"""Route-backed engine registry tests for Morphic Chat CLI."""

from __future__ import annotations

import pytest

from application.use_cases.route_to_engine import EngineStatus
from domain.ports.agent_engine import AgentEngineCapabilities
from domain.ports.engine_registry import EngineRuntimeKind
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.engines.route_engine_registry import RouteEngineRegistry

pytestmark = pytest.mark.asyncio


class _FakeRouteToEngine:
    def __init__(self, statuses: list[EngineStatus]) -> None:
        self._statuses = statuses

    async def list_engines(self) -> list[EngineStatus]:
        return self._statuses

    async def get_engine(self, engine_type: AgentEngineType) -> EngineStatus | None:
        return next(
            (
                status
                for status in self._statuses
                if status.engine_type is engine_type
            ),
            None,
        )


def _status(
    engine_type: AgentEngineType,
    *,
    available: bool,
    max_context_tokens: int = 0,
    supports_sandbox: bool = False,
    supports_streaming: bool = False,
    supports_mcp: bool = False,
    cost_per_hour_usd: float = 0.0,
) -> EngineStatus:
    return EngineStatus(
        engine_type=engine_type,
        available=available,
        capabilities=AgentEngineCapabilities(
            engine_type=engine_type,
            max_context_tokens=max_context_tokens,
            supports_sandbox=supports_sandbox,
            supports_streaming=supports_streaming,
            supports_mcp=supports_mcp,
            cost_per_hour_usd=cost_per_hour_usd,
        ),
    )


async def test_route_engine_registry_maps_engine_status_to_chat_profiles() -> None:
    registry = RouteEngineRegistry(
        _FakeRouteToEngine(
            [
                _status(
                    AgentEngineType.CODEX_CLI,
                    available=True,
                    max_context_tokens=128_000,
                    supports_streaming=True,
                    cost_per_hour_usd=0.25,
                ),
                _status(
                    AgentEngineType.OPENHANDS,
                    available=False,
                    supports_sandbox=True,
                    cost_per_hour_usd=1.50,
                ),
                _status(
                    AgentEngineType.OLLAMA,
                    available=True,
                    supports_streaming=True,
                ),
            ]
        )
    )

    profiles = await registry.list_engines()
    by_id = {profile.id: profile for profile in profiles}

    codex = by_id["codex_cli"]
    assert codex.display_name == "Codex CLI"
    assert codex.kind is EngineRuntimeKind.EXTERNAL_CLI
    assert codex.available is True
    assert codex.context_window == 128_000
    assert codex.supports_streaming is True
    assert codex.supports_editing is True
    assert codex.cost_profile == "paid"

    openhands = by_id["openhands"]
    assert openhands.kind is EngineRuntimeKind.SANDBOX_RUNTIME
    assert openhands.available is False
    assert openhands.supports_sandbox is True
    assert openhands.supports_editing is True

    ollama = by_id["ollama"]
    assert ollama.kind is EngineRuntimeKind.LOCAL_MODEL
    assert ollama.cost_profile == "local"


async def test_route_engine_registry_get_engine_accepts_string_ids() -> None:
    registry = RouteEngineRegistry(
        _FakeRouteToEngine(
            [_status(AgentEngineType.GEMINI_CLI, available=True)]
        )
    )

    profile = await registry.get_engine("gemini_cli")

    assert profile is not None
    assert profile.id == "gemini_cli"
    assert profile.display_name == "Gemini CLI"
    assert await registry.get_engine("missing") is None

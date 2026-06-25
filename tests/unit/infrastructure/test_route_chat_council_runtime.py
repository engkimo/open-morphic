"""Route-backed council runtime tests for Morphic Chat CLI."""

from __future__ import annotations

import pytest

from domain.entities.chat_session import ChatSession, PermissionMode
from domain.entities.council_runtime import CouncilRole
from domain.entities.workspace_context import (
    ContextIndex,
    ContextSourceType,
    WorkspaceContextSource,
)
from domain.ports.agent_engine import AgentEngineResult
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from infrastructure.council.route_chat_council_runtime import RouteChatCouncilRuntime

pytestmark = pytest.mark.asyncio


class _FakeRouteToEngine:
    def __init__(self, results: list[AgentEngineResult]) -> None:
        self._results = results
        self.calls: list[dict[str, object]] = []

    async def execute(self, **kwargs: object) -> AgentEngineResult:
        self.calls.append(kwargs)
        return self._results[len(self.calls) - 1]


def _result(
    engine: AgentEngineType,
    output: str,
    *,
    success: bool = True,
    cost_usd: float = 0.0,
    duration_seconds: float = 0.0,
) -> AgentEngineResult:
    return AgentEngineResult(
        engine=engine,
        success=success,
        output=output,
        cost_usd=cost_usd,
        duration_seconds=duration_seconds,
        error=None if success else "route failed",
    )


def _session() -> ChatSession:
    return ChatSession.start(
        session_id="chat-1",
        goal="Build chat CLI",
        permission_mode=PermissionMode.CONFIRM_DESTRUCTIVE,
    )


def _context() -> ContextIndex:
    return ContextIndex(
        workspace_root="/workspace",
        sources=[
            WorkspaceContextSource(
                source_path="AGENTS.md",
                source_type=ContextSourceType.AGENTS_MD,
                scope="root",
                precedence=1000,
                content_hash="sha256:test",
                sections=["Rules"],
            )
        ],
    )


async def test_route_chat_council_runtime_maps_route_results_to_turns() -> None:
    route = _FakeRouteToEngine(
        [
            _result(
                AgentEngineType.CODEX_CLI,
                "Plan the implementation",
                cost_usd=0.01,
                duration_seconds=1.2,
            ),
            _result(
                AgentEngineType.CLAUDE_CODE,
                "Review the architecture boundary",
                cost_usd=0.02,
                duration_seconds=2.4,
            ),
            _result(
                AgentEngineType.GEMINI_CLI,
                "Proceed with the scoped implementation",
                cost_usd=0.03,
                duration_seconds=3.6,
            ),
        ]
    )

    turns, decision = await RouteChatCouncilRuntime(route).deliberate(
        session=_session(),
        context=_context(),
        user_message="Implement route backed council",
    )

    assert [turn.role for turn in turns] == [
        CouncilRole.PLANNER,
        CouncilRole.CRITIC,
        CouncilRole.LEADER,
    ]
    assert [turn.engine_id for turn in turns] == [
        "codex_cli",
        "claude_code",
        "gemini_cli",
    ]
    assert [turn.content for turn in turns] == [
        "Plan the implementation",
        "Review the architecture boundary",
        "Proceed with the scoped implementation",
    ]
    assert turns[0].cost_usd == 0.01
    assert turns[1].latency_ms == 2400
    assert "context_sources=1" in turns[0].evidence

    assert decision.leader_engine_id == "gemini_cli"
    assert decision.selected_role is CouncilRole.LEADER
    assert decision.selected_content == "Proceed with the scoped implementation"
    assert "planner_engine=codex_cli" in decision.evidence

    assert [call["task_type"] for call in route.calls] == [
        TaskType.CODE_GENERATION,
        TaskType.COMPLEX_REASONING,
        TaskType.COMPLEX_REASONING,
    ]
    assert "Implement route backed council" in str(route.calls[0]["task"])


async def test_route_chat_council_runtime_falls_back_to_local_runtime_on_failure() -> None:
    route = _FakeRouteToEngine(
        [_result(AgentEngineType.CODEX_CLI, "", success=False)]
    )

    turns, decision = await RouteChatCouncilRuntime(route).deliberate(
        session=_session(),
        context=_context(),
        user_message="Plan safely",
    )

    assert route.calls
    assert [turn.engine_id for turn in turns] == ["local", "local", "local"]
    assert decision.leader_engine_id == "local"
    assert "Plan next step for: Plan safely" in decision.selected_content


async def test_route_chat_council_runtime_passes_role_preferred_engines() -> None:
    route = _FakeRouteToEngine(
        [
            _result(AgentEngineType.CODEX_CLI, "Plan"),
            _result(AgentEngineType.CLAUDE_CODE, "Critique"),
            _result(AgentEngineType.GEMINI_CLI, "Lead"),
        ]
    )

    await RouteChatCouncilRuntime(
        route,
        role_engines={
            CouncilRole.PLANNER: AgentEngineType.CODEX_CLI,
            CouncilRole.CRITIC: AgentEngineType.CLAUDE_CODE,
            CouncilRole.LEADER: AgentEngineType.GEMINI_CLI,
        },
    ).deliberate(
        session=_session(),
        context=_context(),
        user_message="Route by role preference",
    )

    assert [call["preferred_engine"] for call in route.calls] == [
        AgentEngineType.CODEX_CLI,
        AgentEngineType.CLAUDE_CODE,
        AgentEngineType.GEMINI_CLI,
    ]

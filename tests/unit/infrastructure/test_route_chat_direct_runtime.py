"""Single-engine route-backed runtime tests for Morphic Chat CLI."""

from __future__ import annotations

import pytest

from domain.entities.agent_engine_event import AgentEngineEvent, AgentEngineEventType
from domain.entities.chat_event import ChatEventType
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
from infrastructure.council.route_chat_direct_runtime import RouteChatDirectRuntime

pytestmark = pytest.mark.asyncio


class _FakeRouteToEngine:
    def __init__(self, result: AgentEngineResult) -> None:
        self._result = result
        self.calls: list[dict[str, object]] = []

    async def execute(self, **kwargs: object) -> AgentEngineResult:
        self.calls.append(kwargs)
        return self._result


class _CollectingEventSink:
    def __init__(self) -> None:
        self.events: list[AgentEngineEvent] = []

    async def publish(self, event: AgentEngineEvent) -> None:
        self.events.append(event)


def _session(
    permission_mode: PermissionMode = PermissionMode.DANGER_FULL_ACCESS,
) -> ChatSession:
    return ChatSession.start(
        session_id="chat-direct-1",
        goal="Fix the failing tests",
        permission_mode=permission_mode,
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


async def test_direct_runtime_makes_one_route_call_and_maps_result() -> None:
    route = _FakeRouteToEngine(
        AgentEngineResult(
            engine=AgentEngineType.CODEX_CLI,
            success=True,
            output="Implemented the fix and ran tests.",
            cost_usd=0.04,
            duration_seconds=2.5,
            metadata={
                "events": [
                    {
                        "type": "run_started",
                        "engine": "codex_cli",
                        "sequence": 0,
                        "session_id": "thread-1",
                        "item_id": None,
                        "item_type": None,
                        "text": None,
                        "payload": {
                            "type": "thread.started",
                            "thread_id": "thread-1",
                        },
                    }
                ]
            },
        )
    )

    turns, decision = await RouteChatDirectRuntime(
        route,
        preferred_engine=AgentEngineType.CODEX_CLI,
    ).deliberate(
        session=_session(),
        context=_context(),
        user_message="Fix the failing tests",
    )

    assert len(route.calls) == 1
    assert route.calls[0]["task"] == "Fix the failing tests"
    assert route.calls[0]["task_type"] is TaskType.CODE_GENERATION
    assert route.calls[0]["preferred_engine"] is AgentEngineType.CODEX_CLI
    assert route.calls[0]["context"] == "context_sources=1; sources=AGENTS.md"
    assert route.calls[0]["workspace_root"] == "/workspace"
    assert route.calls[0]["permission_mode"] is PermissionMode.DANGER_FULL_ACCESS

    assert len(turns) == 1
    assert turns[0].role is CouncilRole.IMPLEMENTER
    assert turns[0].engine_id == "codex_cli"
    assert turns[0].content == "Implemented the fix and ran tests."
    assert turns[0].cost_usd == 0.04
    assert turns[0].latency_ms == 2500
    assert len(turns[0].engine_events) == 1
    assert turns[0].engine_events[0].type is AgentEngineEventType.RUN_STARTED
    assert turns[0].engine_events[0].session_id == "thread-1"
    assert decision.leader_engine_id == "codex_cli"
    assert decision.selected_role is CouncilRole.IMPLEMENTER
    assert decision.selected_content == "Implemented the fix and ran tests."


async def test_direct_runtime_passes_event_sink_to_streaming_route() -> None:
    route = _FakeRouteToEngine(
        AgentEngineResult(
            engine=AgentEngineType.CODEX_CLI,
            success=True,
            output="Done.",
        )
    )
    sink = _CollectingEventSink()

    await RouteChatDirectRuntime(
        route,
        preferred_engine=AgentEngineType.CODEX_CLI,
    ).deliberate_stream(
        session=_session(PermissionMode.WORKSPACE_WRITE),
        context=_context(),
        user_message="Fix tests",
        event_sink=sink,
    )

    assert route.calls[0]["event_sink"] is sink


async def test_direct_runtime_resumes_matching_native_session() -> None:
    route = _FakeRouteToEngine(
        AgentEngineResult(
            engine=AgentEngineType.CODEX_CLI,
            success=True,
            output="Continued.",
        )
    )
    session = ChatSession.start(
        session_id="chat-direct-1",
        permission_mode=PermissionMode.WORKSPACE_WRITE,
    )
    session, _ = session.record_event(
        ChatEventType.CONTEXT_INDEXED,
        {"workspace_root": "/workspace"},
    )
    session, _ = session.record_event(
        ChatEventType.ENGINE_EVENT,
        {"engine": "codex_cli", "session_id": "thread-1"},
    )

    await RouteChatDirectRuntime(
        route,
        preferred_engine=AgentEngineType.CODEX_CLI,
    ).deliberate_stream(
        session=session,
        context=_context(),
        user_message="continue",
        event_sink=_CollectingEventSink(),
    )

    assert route.calls[0]["resume_session_id"] == "thread-1"


async def test_direct_runtime_rejects_resume_in_different_workspace() -> None:
    route = _FakeRouteToEngine(
        AgentEngineResult(
            engine=AgentEngineType.CODEX_CLI,
            success=True,
            output="must not run",
        )
    )
    session = ChatSession.start(
        session_id="chat-direct-1",
        permission_mode=PermissionMode.WORKSPACE_WRITE,
    )
    session, _ = session.record_event(
        ChatEventType.CONTEXT_INDEXED,
        {"workspace_root": "/original"},
    )
    session, _ = session.record_event(
        ChatEventType.ENGINE_EVENT,
        {"engine": "codex_cli", "session_id": "thread-1"},
    )

    with pytest.raises(PermissionError, match="workspace"):
        await RouteChatDirectRuntime(
            route,
            preferred_engine=AgentEngineType.CODEX_CLI,
        ).deliberate_stream(
            session=session,
            context=_context(),
            user_message="continue",
            event_sink=_CollectingEventSink(),
        )

    assert route.calls == []


@pytest.mark.parametrize(
    ("success", "output", "error", "message"),
    [
        (False, "", "engine unavailable", "engine unavailable"),
        (True, "   ", None, "returned no output"),
    ],
)
async def test_direct_runtime_reports_route_failure_without_local_fallback(
    success: bool,
    output: str,
    error: str | None,
    message: str,
) -> None:
    route = _FakeRouteToEngine(
        AgentEngineResult(
            engine=AgentEngineType.CODEX_CLI,
            success=success,
            output=output,
            error=error,
        )
    )

    with pytest.raises(RuntimeError, match=message):
        await RouteChatDirectRuntime(
            route,
            preferred_engine=AgentEngineType.CODEX_CLI,
        ).deliberate(
            session=_session(),
            context=_context(),
            user_message="Fix the failing tests",
        )

    assert len(route.calls) == 1


async def test_direct_runtime_rejects_confirm_destructive_without_prompt_channel() -> None:
    route = _FakeRouteToEngine(
        AgentEngineResult(
            engine=AgentEngineType.CODEX_CLI,
            success=True,
            output="Would have edited files",
        )
    )

    with pytest.raises(PermissionError, match="confirm-destructive"):
        await RouteChatDirectRuntime(
            route,
            preferred_engine=AgentEngineType.CODEX_CLI,
        ).deliberate(
            session=_session(PermissionMode.CONFIRM_DESTRUCTIVE),
            context=_context(),
            user_message="Fix the failing tests",
        )

    assert route.calls == []


async def test_direct_runtime_accepts_workspace_write_for_codex() -> None:
    route = _FakeRouteToEngine(
        AgentEngineResult(
            engine=AgentEngineType.CODEX_CLI,
            success=True,
            output="Edited workspace files",
        )
    )

    await RouteChatDirectRuntime(
        route,
        preferred_engine=AgentEngineType.CODEX_CLI,
    ).deliberate(
        session=_session(PermissionMode.WORKSPACE_WRITE),
        context=_context(),
        user_message="Fix tests",
    )

    assert route.calls[0]["permission_mode"] is PermissionMode.WORKSPACE_WRITE


async def test_direct_runtime_requires_supported_explicit_native_preference(
) -> None:
    route = _FakeRouteToEngine(
        AgentEngineResult(
            engine=AgentEngineType.CODEX_CLI,
            success=True,
            output="unused",
        )
    )

    with pytest.raises(ValueError, match="codex_cli"):
        RouteChatDirectRuntime(route)
    runtime = RouteChatDirectRuntime(
        route,
        preferred_engine=AgentEngineType.CLAUDE_CODE,
    )
    assert runtime._preferred_engine is AgentEngineType.CLAUDE_CODE

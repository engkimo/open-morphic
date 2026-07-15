"""Single-engine route-backed runtime for Morphic Chat CLI."""

from __future__ import annotations

from typing import Protocol

from pydantic import ValidationError

from domain.entities.agent_engine_event import AgentEngineEvent
from domain.entities.chat_session import ChatSession, PermissionMode
from domain.entities.council_runtime import CouncilDecision, CouncilRole, CouncilTurn
from domain.entities.workspace_context import ContextIndex
from domain.ports.agent_engine import AgentEngineEventSinkPort, AgentEngineResult
from domain.ports.council_runtime import StreamingCouncilRuntimePort
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType


class _RouteExecutor(Protocol):
    async def execute(
        self,
        *,
        task: str,
        task_type: TaskType = TaskType.SIMPLE_QA,
        budget: float = 1.0,
        estimated_hours: float = 0.0,
        context_tokens: int = 0,
        preferred_engine: AgentEngineType | None = None,
        timeout_seconds: float = 300.0,
        context: str | None = None,
        workspace_root: str | None = None,
        permission_mode: PermissionMode | None = None,
        event_sink: AgentEngineEventSinkPort | None = None,
        resume_session_id: str | None = None,
        resume_engine: AgentEngineType | None = None,
    ) -> AgentEngineResult: ...


class RouteChatDirectRuntime(StreamingCouncilRuntimePort):
    """Delegate one chat turn to one routed native agent engine."""

    def __init__(
        self,
        route_to_engine: _RouteExecutor,
        *,
        preferred_engine: AgentEngineType | None = None,
        budget: float = 1.0,
        timeout_seconds: float = 300.0,
    ) -> None:
        self._route_to_engine = route_to_engine
        if preferred_engine not in {
            AgentEngineType.CODEX_CLI,
            AgentEngineType.CLAUDE_CODE,
        }:
            raise ValueError(
                "direct route requires an explicit streaming native engine: "
                "codex_cli or claude_code"
            )
        self._preferred_engine = preferred_engine
        self._budget = budget
        self._timeout_seconds = timeout_seconds

    async def deliberate(
        self,
        session: ChatSession,
        context: ContextIndex,
        user_message: str,
    ) -> tuple[list[CouncilTurn], CouncilDecision]:
        return await self._deliberate(
            session=session,
            context=context,
            user_message=user_message,
            event_sink=None,
        )

    async def deliberate_stream(
        self,
        session: ChatSession,
        context: ContextIndex,
        user_message: str,
        event_sink: AgentEngineEventSinkPort,
    ) -> tuple[list[CouncilTurn], CouncilDecision]:
        return await self._deliberate(
            session=session,
            context=context,
            user_message=user_message,
            event_sink=event_sink,
        )

    async def _deliberate(
        self,
        *,
        session: ChatSession,
        context: ContextIndex,
        user_message: str,
        event_sink: AgentEngineEventSinkPort | None,
    ) -> tuple[list[CouncilTurn], CouncilDecision]:
        if session.permission_mode is PermissionMode.CONFIRM_DESTRUCTIVE:
            raise PermissionError(
                "Non-interactive direct route cannot preserve "
                "confirm-destructive approvals"
            )

        native_session = session.native_sessions.get(self._preferred_engine.value)
        if native_session is not None:
            if native_session.workspace_root != context.workspace_root:
                raise PermissionError("native session workspace does not match current workspace")
            if native_session.permission_mode is not session.permission_mode:
                raise PermissionError("native session permission mode does not match current mode")

        result = await self._route_to_engine.execute(
            task=user_message,
            task_type=TaskType.CODE_GENERATION,
            budget=self._budget,
            context_tokens=self._context_tokens(context),
            preferred_engine=self._preferred_engine,
            timeout_seconds=self._timeout_seconds,
            context=self._context_summary(context),
            workspace_root=context.workspace_root,
            permission_mode=session.permission_mode,
            event_sink=event_sink,
            resume_session_id=(
                native_session.session_id if native_session is not None else None
            ),
            resume_engine=(
                native_session.engine if native_session is not None else None
            ),
        )
        if not result.success:
            raise RuntimeError(f"direct route failed: {result.error or 'unknown error'}")
        if not result.output.strip():
            raise RuntimeError("direct route returned no output")

        turn = CouncilTurn(
            role=CouncilRole.IMPLEMENTER,
            engine_id=result.engine.value,
            content=result.output.strip(),
            evidence=[
                f"route_engine={result.engine.value}",
                f"context_sources={len(context.sources)}",
                f"permission={session.permission_mode.value}",
            ],
            engine_events=self._engine_events(result),
            cost_usd=result.cost_usd,
            latency_ms=int(result.duration_seconds * 1000),
        )
        decision = CouncilDecision(
            leader_engine_id=turn.engine_id,
            selected_role=CouncilRole.IMPLEMENTER,
            selected_content=turn.content,
            rationale="Single-engine direct route completed the native agent task.",
            evidence=turn.evidence,
        )
        return [turn], decision

    def _engine_events(self, result: AgentEngineResult) -> list[AgentEngineEvent]:
        raw_events = result.metadata.get("events")
        if not isinstance(raw_events, list):
            return []
        events: list[AgentEngineEvent] = []
        for raw_event in raw_events:
            try:
                events.append(AgentEngineEvent.model_validate(raw_event, strict=False))
            except ValidationError:
                continue
        return events

    def _context_tokens(self, context: ContextIndex) -> int:
        return sum(len(source.sections) for source in context.sources)

    def _context_summary(self, context: ContextIndex) -> str:
        sources = ", ".join(source.source_path for source in context.sources[:10])
        return f"context_sources={len(context.sources)}; sources={sources}"

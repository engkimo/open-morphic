"""Route-backed council runtime for Morphic Chat CLI."""

from __future__ import annotations

from typing import Protocol

from domain.entities.chat_session import ChatSession
from domain.entities.council_runtime import CouncilDecision, CouncilRole, CouncilTurn
from domain.entities.workspace_context import ContextIndex
from domain.ports.agent_engine import AgentEngineResult
from domain.ports.council_runtime import CouncilRuntimePort
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from infrastructure.council.local_chat_council_runtime import LocalChatCouncilRuntime


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
    ) -> AgentEngineResult: ...


class RouteChatCouncilRuntime(CouncilRuntimePort):
    """Delegate planner/critic/leader roles to the existing engine router."""

    def __init__(
        self,
        route_to_engine: _RouteExecutor,
        *,
        fallback: CouncilRuntimePort | None = None,
        role_engines: dict[CouncilRole, AgentEngineType] | None = None,
        budget: float = 1.0,
        timeout_seconds: float = 300.0,
    ) -> None:
        self._route_to_engine = route_to_engine
        self._fallback = fallback or LocalChatCouncilRuntime()
        self._role_engines = role_engines or {}
        self._budget = budget
        self._timeout_seconds = timeout_seconds

    async def deliberate(
        self,
        session: ChatSession,
        context: ContextIndex,
        user_message: str,
    ) -> tuple[list[CouncilTurn], CouncilDecision]:
        try:
            planner = await self._run_role(
                role=CouncilRole.PLANNER,
                session=session,
                context=context,
                user_message=user_message,
                prior_turns=[],
                task_type=TaskType.CODE_GENERATION,
            )
            critic = await self._run_role(
                role=CouncilRole.CRITIC,
                session=session,
                context=context,
                user_message=user_message,
                prior_turns=[planner],
                task_type=TaskType.COMPLEX_REASONING,
            )
            leader = await self._run_role(
                role=CouncilRole.LEADER,
                session=session,
                context=context,
                user_message=user_message,
                prior_turns=[planner, critic],
                task_type=TaskType.COMPLEX_REASONING,
            )
        except Exception:
            return await self._fallback.deliberate(session, context, user_message)

        turns = [planner, critic, leader]
        decision = CouncilDecision(
            leader_engine_id=leader.engine_id,
            selected_role=CouncilRole.LEADER,
            selected_content=leader.content,
            rationale="Route-backed council leader selected the final response.",
            evidence=[
                f"planner_engine={planner.engine_id}",
                f"critic_engine={critic.engine_id}",
                f"leader_engine={leader.engine_id}",
                f"context_sources={len(context.sources)}",
            ],
            rejected_options=[critic.content],
        )
        return turns, decision

    async def _run_role(
        self,
        *,
        role: CouncilRole,
        session: ChatSession,
        context: ContextIndex,
        user_message: str,
        prior_turns: list[CouncilTurn],
        task_type: TaskType,
    ) -> CouncilTurn:
        result = await self._route_to_engine.execute(
            task=self._prompt_for(
                role=role,
                session=session,
                context=context,
                user_message=user_message,
                prior_turns=prior_turns,
            ),
            task_type=task_type,
            budget=self._budget,
            context_tokens=self._context_tokens(context),
            preferred_engine=self._role_engines.get(role),
            timeout_seconds=self._timeout_seconds,
            context=self._context_summary(context),
        )
        if not result.success or not result.output.strip():
            raise RuntimeError(result.error or "route engine returned no output")

        return CouncilTurn(
            role=role,
            engine_id=result.engine.value,
            content=result.output.strip(),
            evidence=[
                f"route_engine={result.engine.value}",
                f"context_sources={len(context.sources)}",
                f"permission={session.permission_mode.value}",
            ],
            cost_usd=result.cost_usd,
            latency_ms=int(result.duration_seconds * 1000),
        )

    def _prompt_for(
        self,
        *,
        role: CouncilRole,
        session: ChatSession,
        context: ContextIndex,
        user_message: str,
        prior_turns: list[CouncilTurn],
    ) -> str:
        prior = "\n".join(
            f"{turn.role.value}: {turn.content}" for turn in prior_turns
        )
        if role is CouncilRole.PLANNER:
            instruction = "Propose the smallest verifiable implementation plan."
        elif role is CouncilRole.CRITIC:
            instruction = "Review the plan for architecture, safety, and tests."
        else:
            instruction = "Select the final response based on evidence."

        return "\n".join(
            part
            for part in [
                f"Role: {role.value}",
                instruction,
                f"Session: {session.id}",
                f"Permission mode: {session.permission_mode.value}",
                f"Context sources: {len(context.sources)}",
                f"User message: {user_message}",
                "Prior turns:",
                prior,
            ]
            if part
        )

    def _context_tokens(self, context: ContextIndex) -> int:
        return sum(len(source.sections) for source in context.sources)

    def _context_summary(self, context: ContextIndex) -> str:
        sources = ", ".join(source.source_path for source in context.sources[:10])
        return f"context_sources={len(context.sources)}; sources={sources}"

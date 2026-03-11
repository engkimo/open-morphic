"""HandoffTaskUseCase — cross-agent task handoff with full state preservation.

Flow:
1. Load/create SharedTaskState
2. Record "handoff" AgentAction on source engine
3. Add Decision (reason for handoff)
4. Build adapter-injected context for target
5. Call RouteToEngineUseCase.execute() with target as preferred_engine
6. Record "received_handoff" AgentAction on target
7. Optional insight extraction
8. Persist state
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from domain.entities.cognitive import AgentAction, Decision, SharedTaskState
from domain.ports.agent_engine import AgentEngineResult
from domain.ports.context_adapter import ContextAdapterPort
from domain.ports.shared_task_state_repository import SharedTaskStateRepository
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType

logger = logging.getLogger(__name__)


@dataclass
class HandoffRequest:
    """Request to hand off a task from one engine to another."""

    task: str
    task_id: str
    source_engine: AgentEngineType
    reason: str
    target_engine: AgentEngineType | None = None  # None = let router decide
    task_type: TaskType = TaskType.COMPLEX_REASONING
    budget: float = 1.0
    estimated_hours: float = 0.0
    context_tokens: int = 0
    model: str | None = None
    timeout_seconds: float = 300.0
    extract_insights: bool = False
    artifacts: dict[str, str] = field(default_factory=dict)


@dataclass
class HandoffResult:
    """Result of a task handoff operation."""

    success: bool
    source_engine: AgentEngineType
    target_engine: AgentEngineType
    engine_result: AgentEngineResult | None = None
    state: SharedTaskState | None = None
    error: str | None = None


class HandoffTaskUseCase:
    """Orchestrate cross-agent task handoff with full state preservation."""

    def __init__(
        self,
        route_to_engine: object,  # RouteToEngineUseCase (avoid circular)
        task_state_repo: SharedTaskStateRepository,
        context_adapters: dict[AgentEngineType, ContextAdapterPort] | None = None,
        insight_extractor: object | None = None,  # ExtractInsightsUseCase
    ) -> None:
        self._route_to_engine = route_to_engine
        self._task_state_repo = task_state_repo
        self._context_adapters = context_adapters or {}
        self._insight_extractor = insight_extractor

    async def handoff(self, request: HandoffRequest) -> HandoffResult:
        """Execute a task handoff from source engine to target engine."""
        try:
            # 1. Load or create SharedTaskState
            state = await self._task_state_repo.get(request.task_id)
            if state is None:
                state = SharedTaskState(task_id=request.task_id)

            # 2. Record "handoff" action on source engine
            state.add_action(
                AgentAction(
                    agent_engine=request.source_engine,
                    action_type="handoff",
                    summary=(
                        f"Handing off to "
                        f"{request.target_engine.value if request.target_engine else 'router'}"
                        f": {request.reason}"
                    ),
                )
            )

            # 3. Add Decision (reason for handoff)
            state.add_decision(
                Decision(
                    description=f"Handoff from {request.source_engine.value}",
                    rationale=request.reason,
                    agent_engine=request.source_engine,
                    confidence=0.7,
                )
            )

            # 4. Merge request artifacts into state
            for key, value in request.artifacts.items():
                state.add_artifact(key, value)

            # 5. Persist intermediate state
            await self._task_state_repo.save(state)

            # 6. Build adapter-injected context for target
            target = request.target_engine
            context = self._build_handoff_context(state, target)

            # 7. Execute via RouteToEngineUseCase
            engine_result = await self._route_to_engine.execute(  # type: ignore[union-attr]
                task=request.task,
                task_type=request.task_type,
                budget=request.budget,
                estimated_hours=request.estimated_hours,
                context_tokens=request.context_tokens,
                preferred_engine=target,
                model=request.model,
                timeout_seconds=request.timeout_seconds,
                context=context,
                task_id=request.task_id,
            )

            actual_target = engine_result.engine

            # 8. Record "received_handoff" action on target
            state.add_action(
                AgentAction(
                    agent_engine=actual_target,
                    action_type="received_handoff",
                    summary=f"Received handoff from {request.source_engine.value}",
                    cost_usd=engine_result.cost_usd,
                    duration_seconds=engine_result.duration_seconds,
                )
            )

            # 9. Optional insight extraction
            if request.extract_insights and self._insight_extractor and engine_result.success:
                try:
                    await self._insight_extractor.extract_and_store(  # type: ignore[union-attr]
                        task_id=request.task_id,
                        engine=actual_target,
                        output=engine_result.output,
                    )
                except Exception:
                    logger.debug("Insight extraction failed for handoff task=%s", request.task_id)

            # 10. Persist final state
            await self._task_state_repo.save(state)

            return HandoffResult(
                success=engine_result.success,
                source_engine=request.source_engine,
                target_engine=actual_target,
                engine_result=engine_result,
                state=state,
            )

        except Exception as exc:
            logger.error("Handoff failed for task=%s: %s", request.task_id, exc)
            return HandoffResult(
                success=False,
                source_engine=request.source_engine,
                target_engine=request.target_engine or AgentEngineType.OLLAMA,
                error=str(exc),
            )

    def _build_handoff_context(
        self,
        state: SharedTaskState,
        target_engine: AgentEngineType | None,
    ) -> str:
        """Build context string for the target engine.

        Uses ContextAdapterPort if available, otherwise builds a plain text summary.
        """
        if target_engine and self._context_adapters:
            adapter = self._context_adapters.get(target_engine)
            if adapter:
                return adapter.inject_context(state=state, memory_context="")

        # Fallback: plain text summary
        parts = [f"## Handoff Context (task: {state.task_id})"]

        if state.decisions:
            parts.append("\n### Prior Decisions")
            for d in state.decisions[-5:]:  # Last 5 decisions
                parts.append(f"- [{d.agent_engine.value}] {d.description}")

        if state.artifacts:
            parts.append("\n### Artifacts")
            for k, v in list(state.artifacts.items())[:10]:
                parts.append(f"- {k}: {v[:200]}")

        if state.blockers:
            parts.append("\n### Blockers")
            for b in state.blockers:
                parts.append(f"- {b}")

        if state.agent_history:
            parts.append("\n### Recent Actions")
            for a in state.agent_history[-5:]:
                parts.append(f"- [{a.agent_engine.value}] {a.action_type}: {a.summary[:100]}")

        return "\n".join(parts)

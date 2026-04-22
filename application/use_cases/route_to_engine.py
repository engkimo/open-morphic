"""RouteToEngineUseCase — select best agent engine and execute task.

Bridges the gap between AgentEngineRouter (domain service, pure logic)
and AgentEnginePort drivers (infrastructure). Iterates the fallback chain
until one engine succeeds or all fail.

Sprint 7.4: Adds affinity-aware routing, adapter context injection, and action recording.
Sprint 23.1: Adds fallback attempt tracking (BUG-003) and engine cost recording (BUG-002).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain.entities.cognitive import AgentAction
from domain.ports.agent_engine import AgentEngineCapabilities, AgentEnginePort, AgentEngineResult
from domain.ports.context_adapter import ContextAdapterPort
from domain.services.agent_engine_router import AgentEngineRouter
from domain.services.topic_extractor import TopicExtractor
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.fallback_attempt import FallbackAttempt
from domain.value_objects.model_tier import TaskType

if TYPE_CHECKING:
    from infrastructure.llm.cost_tracker import CostTracker

logger = logging.getLogger(__name__)

# Lazy imports to avoid circular — these are optional deps
_AgentAffinityRepository = None
_SharedTaskStateRepository = None


@dataclass
class EngineStatus:
    """Availability snapshot of a single engine."""

    engine_type: AgentEngineType
    available: bool
    capabilities: AgentEngineCapabilities


class RouteToEngineUseCase:
    """Route tasks to the best available agent execution engine.

    Pure application logic — depends only on domain ports and services.
    """

    def __init__(
        self,
        drivers: dict[AgentEngineType, AgentEnginePort],
        context_adapters: dict[AgentEngineType, ContextAdapterPort] | None = None,
        affinity_repo: object | None = None,  # AgentAffinityRepository
        task_state_repo: object | None = None,  # SharedTaskStateRepository
        affinity_min_samples: int = 3,
        affinity_boost_threshold: float = 0.6,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self._drivers = drivers
        self._context_adapters = context_adapters
        self._affinity_repo = affinity_repo
        self._task_state_repo = task_state_repo
        self._affinity_min_samples = affinity_min_samples
        self._affinity_boost_threshold = affinity_boost_threshold
        self._cost_tracker = cost_tracker

    async def list_engines(self) -> list[EngineStatus]:
        """Return all registered engines with current availability."""
        results: list[EngineStatus] = []
        for engine_type, driver in self._drivers.items():
            available = await driver.is_available()
            capabilities = driver.get_capabilities()
            results.append(
                EngineStatus(
                    engine_type=engine_type,
                    available=available,
                    capabilities=capabilities,
                )
            )
        return results

    async def get_engine(self, engine_type: AgentEngineType) -> EngineStatus | None:
        """Return status of a single engine, or None if not registered."""
        driver = self._drivers.get(engine_type)
        if driver is None:
            return None
        available = await driver.is_available()
        capabilities = driver.get_capabilities()
        return EngineStatus(
            engine_type=engine_type,
            available=available,
            capabilities=capabilities,
        )

    async def execute(
        self,
        task: str,
        task_type: TaskType = TaskType.SIMPLE_QA,
        budget: float = 1.0,
        estimated_hours: float = 0.0,
        context_tokens: int = 0,
        preferred_engine: AgentEngineType | None = None,
        model: str | None = None,
        timeout_seconds: float = 300.0,
        context: str | None = None,
        task_id: str | None = None,
    ) -> AgentEngineResult:
        """Route to best available engine and execute.

        If *preferred_engine* is set, try it first then fall back.
        Otherwise, use AgentEngineRouter for ordering (affinity-aware if data available).
        Iterates chain: is_available() → run_task() → return on first success.
        If all engines fail, returns the last error result.

        *context* is prepended to *task* when provided (knowledge file injection).
        *task_id* enables adapter context injection and action recording.

        BUG-003: Every attempt is recorded as a FallbackAttempt for transparency.
        BUG-002: Successful engine costs are recorded via CostTracker.
        """
        # Extract topic for affinity lookup
        topic = TopicExtractor.extract(task)

        # Build engine chain (affinity-aware when data available)
        chain = await self._build_chain(
            task_type=task_type,
            budget=budget,
            estimated_hours=estimated_hours,
            context_tokens=context_tokens,
            preferred_engine=preferred_engine,
            topic=topic,
        )

        engines_tried = [e.value for e in chain]
        attempts: list[FallbackAttempt] = []
        last_result: AgentEngineResult | None = None

        for engine_type in chain:
            driver = self._drivers.get(engine_type)
            if driver is None:
                logger.debug("Engine %s not registered, skipping", engine_type.value)
                attempts.append(
                    FallbackAttempt(
                        engine=engine_type.value,
                        attempted=False,
                        skip_reason="not_registered",
                    )
                )
                continue

            if not await driver.is_available():
                logger.info("Engine %s unavailable, trying next", engine_type.value)
                attempts.append(
                    FallbackAttempt(
                        engine=engine_type.value,
                        attempted=False,
                        skip_reason="unavailable",
                    )
                )
                continue

            # Build effective task with context injection
            effective_task = await self._build_effective_task(
                task=task,
                context=context,
                engine_type=engine_type,
                task_id=task_id,
            )

            start = time.monotonic()
            try:
                result = await driver.run_task(
                    task=effective_task,
                    model=model,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:
                elapsed = time.monotonic() - start
                logger.warning(
                    "Engine %s raised %s after %.1fs",
                    engine_type.value,
                    type(exc).__name__,
                    elapsed,
                )
                attempts.append(
                    FallbackAttempt(
                        engine=engine_type.value,
                        attempted=True,
                        skip_reason="exception",
                        error=str(exc),
                        duration_seconds=elapsed,
                    )
                )
                last_result = AgentEngineResult(
                    engine=engine_type,
                    success=False,
                    output="",
                    error=str(exc),
                    duration_seconds=elapsed,
                )
                continue

            elapsed = time.monotonic() - start
            if result.success:
                logger.info("Engine %s succeeded", engine_type.value)
                attempts.append(
                    FallbackAttempt(
                        engine=engine_type.value,
                        attempted=True,
                        duration_seconds=elapsed,
                    )
                )
                # Attach fallback context to result
                result.engines_tried = engines_tried
                result.fallback_attempts = attempts
                if len(attempts) > 1:
                    result.fallback_reason = self._determine_fallback_reason(attempts)
                # Fire-and-forget: update affinity + record action + record cost
                await self._post_success(
                    engine_type=engine_type,
                    topic=topic,
                    task_id=task_id,
                    result=result,
                    start_time=start,
                )
                return result

            logger.info("Engine %s returned failure, trying next", engine_type.value)
            attempts.append(
                FallbackAttempt(
                    engine=engine_type.value,
                    attempted=True,
                    skip_reason="failure",
                    error=result.error,
                    duration_seconds=elapsed,
                )
            )
            last_result = result

        # All engines failed — return last error or a generic failure
        if last_result is not None:
            last_result.engines_tried = engines_tried
            last_result.fallback_attempts = attempts
            last_result.fallback_reason = self._determine_fallback_reason(attempts)
            return last_result

        no_engines = AgentEngineResult(
            engine=AgentEngineType.OLLAMA,
            success=False,
            output="",
            error="No engines available",
            engines_tried=engines_tried,
            fallback_attempts=attempts,
            fallback_reason="no_engines_available",
        )
        return no_engines

    @staticmethod
    def _determine_fallback_reason(attempts: list[FallbackAttempt]) -> str | None:
        """Summarize why fallback occurred from the attempt history."""
        reasons: list[str] = []
        for a in attempts:
            if a.skip_reason:
                reasons.append(f"{a.engine}:{a.skip_reason}")
        return "; ".join(reasons) if reasons else None

    async def _build_chain(
        self,
        task_type: TaskType,
        budget: float,
        estimated_hours: float,
        context_tokens: int,
        preferred_engine: AgentEngineType | None,
        topic: str = "general",
    ) -> list[AgentEngineType]:
        """Build ordered engine chain. Preferred engine goes first if set."""
        if preferred_engine is not None:
            # Start with preferred, then add router fallbacks (deduped)
            chain = [preferred_engine]
            router_chain = AgentEngineRouter.select_with_fallbacks(
                task_type=task_type,
                budget=budget,
                estimated_hours=estimated_hours,
                context_tokens=context_tokens,
            )
            for engine in router_chain:
                if engine not in chain:
                    chain.append(engine)
            return chain

        # Try affinity-aware routing
        affinities = await self._fetch_affinities(topic)
        if affinities:
            return AgentEngineRouter.select_with_affinity(
                task_type=task_type,
                budget=budget,
                estimated_hours=estimated_hours,
                context_tokens=context_tokens,
                affinities=affinities,
                min_samples=self._affinity_min_samples,
                boost_threshold=self._affinity_boost_threshold,
            )

        return AgentEngineRouter.select_with_fallbacks(
            task_type=task_type,
            budget=budget,
            estimated_hours=estimated_hours,
            context_tokens=context_tokens,
        )

    async def _build_effective_task(
        self,
        task: str,
        context: str | None,
        engine_type: AgentEngineType,
        task_id: str | None,
    ) -> str:
        """Build the effective task string with context injection.

        Uses ContextAdapterPort when available and task_id is set,
        falls back to simple string prepend.
        """
        # Try adapter-based context injection
        if task_id and self._context_adapters and self._task_state_repo:
            adapter = self._context_adapters.get(engine_type)
            if adapter:
                state = await self._task_state_repo.get(task_id)  # type: ignore[union-attr]
                if state is not None:
                    memory_ctx = context or ""
                    injected = adapter.inject_context(
                        state=state,
                        memory_context=memory_ctx,
                    )
                    return f"{injected}\n\n---\n\nTask: {task}"

        # Fallback: simple string prepend
        if context:
            return f"{context}\n\n---\n\nTask: {task}"
        return task

    async def _fetch_affinities(self, topic: str) -> list:
        """Fetch affinity scores for a topic. Returns [] if no repo."""
        if self._affinity_repo is None:
            return []
        try:
            return await self._affinity_repo.get_by_topic(topic)  # type: ignore[union-attr]
        except Exception:
            logger.debug("Failed to fetch affinities for topic=%s", topic)
            return []

    async def _post_success(
        self,
        engine_type: AgentEngineType,
        topic: str,
        task_id: str | None,
        result: AgentEngineResult,
        start_time: float,
    ) -> None:
        """Post-success: update affinity, record action, record cost (fire-and-forget)."""
        elapsed = time.monotonic() - start_time

        # Update affinity
        await self._update_affinity(engine_type, topic, success=True)

        # Record action to SharedTaskState
        await self._record_action(
            task_id=task_id,
            engine_type=engine_type,
            result=result,
            duration=elapsed,
        )

        # BUG-002 fix: record engine cost to CostRecord
        await self._record_engine_cost(result)

    async def _update_affinity(
        self,
        engine_type: AgentEngineType,
        topic: str,
        success: bool,
    ) -> None:
        """Update affinity score after execution (fire-and-forget)."""
        if self._affinity_repo is None:
            return
        try:
            from domain.entities.cognitive import AgentAffinityScore

            existing = await self._affinity_repo.get(engine_type, topic)  # type: ignore[union-attr]
            if existing is not None:
                # Incremental update
                new_count = existing.sample_count + 1
                # Exponential moving average for success_rate
                alpha = 0.2
                success_val = 1.0 if success else 0.0
                new_success = existing.success_rate * (1 - alpha) + success_val * alpha
                updated = AgentAffinityScore(
                    engine=engine_type,
                    topic=topic,
                    familiarity=min(1.0, existing.familiarity + 0.05),
                    recency=1.0,
                    success_rate=new_success,
                    cost_efficiency=existing.cost_efficiency,
                    sample_count=new_count,
                )
            else:
                updated = AgentAffinityScore(
                    engine=engine_type,
                    topic=topic,
                    familiarity=0.1,
                    recency=1.0,
                    success_rate=1.0 if success else 0.0,
                    cost_efficiency=0.5,
                    sample_count=1,
                )
            await self._affinity_repo.upsert(updated)  # type: ignore[union-attr]
        except Exception:
            logger.debug("Failed to update affinity for %s/%s", engine_type.value, topic)

    async def _record_action(
        self,
        task_id: str | None,
        engine_type: AgentEngineType,
        result: AgentEngineResult,
        duration: float,
    ) -> None:
        """Record agent action to SharedTaskState (fire-and-forget)."""
        if task_id is None or self._task_state_repo is None:
            return
        try:
            action = AgentAction(
                agent_engine=engine_type,
                action_type="execute",
                summary=result.output[:200] if result.output else "",
                cost_usd=result.cost_usd,
                duration_seconds=duration,
            )
            await self._task_state_repo.append_action(task_id, action)  # type: ignore[union-attr]
        except Exception:
            logger.debug("Failed to record action for task=%s", task_id)

    async def _record_engine_cost(self, result: AgentEngineResult) -> None:
        """Record engine execution cost to CostRecord (BUG-002 fix, fire-and-forget)."""
        if self._cost_tracker is None:
            return
        try:
            await self._cost_tracker.record_engine_result(result)
        except Exception:
            logger.debug("Failed to record engine cost for %s", result.engine.value)

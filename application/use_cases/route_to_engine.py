"""RouteToEngineUseCase — select best agent engine and execute task.

Bridges the gap between AgentEngineRouter (domain service, pure logic)
and AgentEnginePort drivers (infrastructure). Iterates the fallback chain
until one engine succeeds or all fail.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from domain.ports.agent_engine import AgentEngineCapabilities, AgentEnginePort, AgentEngineResult
from domain.services.agent_engine_router import AgentEngineRouter
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType

logger = logging.getLogger(__name__)


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

    def __init__(self, drivers: dict[AgentEngineType, AgentEnginePort]) -> None:
        self._drivers = drivers

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
    ) -> AgentEngineResult:
        """Route to best available engine and execute.

        If *preferred_engine* is set, try it first then fall back.
        Otherwise, use AgentEngineRouter.select_with_fallbacks() for ordering.
        Iterates chain: is_available() → run_task() → return on first success.
        If all engines fail, returns the last error result.
        """
        chain = self._build_chain(
            task_type=task_type,
            budget=budget,
            estimated_hours=estimated_hours,
            context_tokens=context_tokens,
            preferred_engine=preferred_engine,
        )

        last_result: AgentEngineResult | None = None

        for engine_type in chain:
            driver = self._drivers.get(engine_type)
            if driver is None:
                logger.debug("Engine %s not registered, skipping", engine_type.value)
                continue

            if not await driver.is_available():
                logger.info("Engine %s unavailable, trying next", engine_type.value)
                continue

            start = time.monotonic()
            try:
                result = await driver.run_task(
                    task=task,
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
                last_result = AgentEngineResult(
                    engine=engine_type,
                    success=False,
                    output="",
                    error=str(exc),
                    duration_seconds=elapsed,
                )
                continue

            if result.success:
                logger.info("Engine %s succeeded", engine_type.value)
                return result

            logger.info("Engine %s returned failure, trying next", engine_type.value)
            last_result = result

        # All engines failed — return last error or a generic failure
        if last_result is not None:
            return last_result

        return AgentEngineResult(
            engine=AgentEngineType.OLLAMA,
            success=False,
            output="",
            error="No engines available",
        )

    def _build_chain(
        self,
        task_type: TaskType,
        budget: float,
        estimated_hours: float,
        context_tokens: int,
        preferred_engine: AgentEngineType | None,
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

        return AgentEngineRouter.select_with_fallbacks(
            task_type=task_type,
            budget=budget,
            estimated_hours=estimated_hours,
            context_tokens=context_tokens,
        )

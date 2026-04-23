"""EngineCostRecorderPort — record agent-engine execution costs.

Narrow port: callers (RouteToEngineUseCase) only need to *record* a
completed engine result. Aggregation/query helpers live in
`infrastructure.llm.CostTracker` and are not exposed through this port —
the UseCase doesn't need them.

If a future application-layer caller needs aggregation, add a separate
read-side port rather than fattening this one.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.ports.agent_engine import AgentEngineResult


class EngineCostRecorderPort(ABC):
    @abstractmethod
    async def record_engine_result(self, result: AgentEngineResult) -> None: ...

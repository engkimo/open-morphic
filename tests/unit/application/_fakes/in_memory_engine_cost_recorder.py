"""In-memory EngineCostRecorderPort fake for unit tests.

Stores recorded results in `self.records`. Tests can inspect the list
to assert "this UseCase recorded cost N times for engine X".
"""

from __future__ import annotations

from domain.ports.agent_engine import AgentEngineResult
from domain.ports.engine_cost_recorder import EngineCostRecorderPort


class InMemoryEngineCostRecorder(EngineCostRecorderPort):
    def __init__(self) -> None:
        self.records: list[AgentEngineResult] = []

    async def record_engine_result(self, result: AgentEngineResult) -> None:
        self.records.append(result)

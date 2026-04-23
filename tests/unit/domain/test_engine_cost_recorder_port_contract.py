"""Contract tests for EngineCostRecorderPort.

Run against the in-memory fake. CostTracker (file-backed via
CostRepository) is exercised in its own infra suite; LSP locked via
isinstance assertion in tests/unit/infrastructure/test_cost_tracker.py.
"""

from __future__ import annotations

import pytest

from domain.ports.agent_engine import AgentEngineResult
from domain.ports.engine_cost_recorder import EngineCostRecorderPort
from domain.value_objects.agent_engine import AgentEngineType
from tests.unit.application._fakes.in_memory_engine_cost_recorder import (
    InMemoryEngineCostRecorder,
)


@pytest.fixture
def recorder() -> InMemoryEngineCostRecorder:
    return InMemoryEngineCostRecorder()


class TestEngineCostRecorderPortContract:
    async def test_starts_empty(self, recorder: EngineCostRecorderPort) -> None:
        assert isinstance(recorder, InMemoryEngineCostRecorder)
        assert recorder.records == []

    async def test_records_appended_in_call_order(
        self, recorder: InMemoryEngineCostRecorder
    ) -> None:
        first = AgentEngineResult(
            engine=AgentEngineType.OLLAMA,
            success=True,
            output="ok",
            cost_usd=0.0,
        )
        second = AgentEngineResult(
            engine=AgentEngineType.CLAUDE_CODE,
            success=True,
            output="ok",
            cost_usd=0.05,
        )
        await recorder.record_engine_result(first)
        await recorder.record_engine_result(second)

        assert recorder.records == [first, second]

    async def test_records_failure_results_too(
        self, recorder: InMemoryEngineCostRecorder
    ) -> None:
        failure = AgentEngineResult(
            engine=AgentEngineType.OPENHANDS,
            success=False,
            output="",
            error="boom",
            cost_usd=0.0,
        )
        await recorder.record_engine_result(failure)
        assert recorder.records[0].success is False

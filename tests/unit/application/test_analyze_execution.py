"""Tests for AnalyzeExecutionUseCase."""

from __future__ import annotations

import pytest

from application.use_cases.analyze_execution import AnalyzeExecutionUseCase
from domain.entities.execution_record import ExecutionRecord
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from infrastructure.persistence.in_memory_execution_record import (
    InMemoryExecutionRecordRepository,
)


def _rec(
    success: bool = True,
    task_type: TaskType = TaskType.SIMPLE_QA,
    engine: AgentEngineType = AgentEngineType.OLLAMA,
    model: str = "ollama/qwen3:8b",
    cost: float = 0.01,
    error: str | None = None,
) -> ExecutionRecord:
    return ExecutionRecord(
        task_id="t1",
        task_type=task_type,
        engine_used=engine,
        model_used=model,
        success=success,
        cost_usd=cost,
        error_message=error,
    )


class TestAnalyzeExecution:
    def setup_method(self) -> None:
        self.repo = InMemoryExecutionRecordRepository()
        self.uc = AnalyzeExecutionUseCase(repo=self.repo)

    @pytest.mark.asyncio
    async def test_record_saves(self) -> None:
        record = _rec()
        await self.uc.record(record)
        all_records = await self.repo.list_recent()
        assert len(all_records) == 1

    @pytest.mark.asyncio
    async def test_get_stats_empty(self) -> None:
        stats = await self.uc.get_stats()
        assert stats.total_count == 0

    @pytest.mark.asyncio
    async def test_get_stats_with_data(self) -> None:
        await self.uc.record(_rec(success=True, cost=0.10))
        await self.uc.record(_rec(success=False, cost=0.05))
        stats = await self.uc.get_stats()
        assert stats.total_count == 2
        assert stats.success_count == 1

    @pytest.mark.asyncio
    async def test_get_stats_by_task_type(self) -> None:
        await self.uc.record(_rec(task_type=TaskType.SIMPLE_QA))
        await self.uc.record(_rec(task_type=TaskType.CODE_GENERATION))
        stats = await self.uc.get_stats(task_type=TaskType.SIMPLE_QA)
        assert stats.total_count == 1

    @pytest.mark.asyncio
    async def test_failure_patterns_empty(self) -> None:
        patterns = await self.uc.get_failure_patterns()
        assert patterns == []

    @pytest.mark.asyncio
    async def test_failure_patterns_grouped(self) -> None:
        await self.uc.record(_rec(success=False, error="Connection timeout"))
        await self.uc.record(_rec(success=False, error="Connection timeout"))
        await self.uc.record(_rec(success=False, error="File not found"))
        patterns = await self.uc.get_failure_patterns()
        assert len(patterns) == 2
        # Most common first
        assert patterns[0].count == 2
        assert patterns[0].error_pattern == "Connection timeout"

    @pytest.mark.asyncio
    async def test_failure_patterns_include_metadata(self) -> None:
        await self.uc.record(
            _rec(
                success=False,
                error="timeout",
                task_type=TaskType.SIMPLE_QA,
                engine=AgentEngineType.OLLAMA,
            )
        )
        patterns = await self.uc.get_failure_patterns()
        assert "simple_qa" in patterns[0].task_types
        assert "ollama" in patterns[0].engines

    @pytest.mark.asyncio
    async def test_failure_patterns_limit(self) -> None:
        for i in range(5):
            await self.uc.record(_rec(success=False, error=f"Error {i}"))
        patterns = await self.uc.get_failure_patterns(limit=3)
        assert len(patterns) == 3

    @pytest.mark.asyncio
    async def test_get_model_distribution(self) -> None:
        await self.uc.record(_rec(model="ollama/qwen3:8b"))
        await self.uc.record(_rec(model="ollama/qwen3:8b"))
        await self.uc.record(_rec(model="claude-sonnet-4-6"))
        dist = await self.uc.get_model_distribution()
        assert dist["ollama/qwen3:8b"] == 2
        assert dist["claude-sonnet-4-6"] == 1

    @pytest.mark.asyncio
    async def test_get_model_distribution_empty(self) -> None:
        dist = await self.uc.get_model_distribution()
        assert dist == {}

    @pytest.mark.asyncio
    async def test_normalize_error_truncates_long(self) -> None:
        long_error = "Error: " + "x" * 200
        normalized = AnalyzeExecutionUseCase._normalize_error(long_error)
        assert len(normalized) <= 80

    @pytest.mark.asyncio
    async def test_normalize_error_first_line(self) -> None:
        error = "First line error\nStack trace\nMore details"
        normalized = AnalyzeExecutionUseCase._normalize_error(error)
        assert normalized == "First line error"

    @pytest.mark.asyncio
    async def test_failure_patterns_unknown_error(self) -> None:
        await self.uc.record(_rec(success=False, error=None))
        patterns = await self.uc.get_failure_patterns()
        assert len(patterns) == 1
        assert patterns[0].error_pattern == "unknown"

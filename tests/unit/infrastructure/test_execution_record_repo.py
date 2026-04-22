"""Tests for InMemoryExecutionRecordRepository."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from domain.entities.execution_record import ExecutionRecord
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from infrastructure.persistence.in_memory_execution_record import (
    InMemoryExecutionRecordRepository,
)


def _rec(
    task_type: TaskType = TaskType.SIMPLE_QA,
    engine: AgentEngineType = AgentEngineType.OLLAMA,
    success: bool = True,
    cost: float = 0.01,
    duration: float = 1.0,
    model: str = "ollama/qwen3:8b",
    error: str | None = None,
    created_at: datetime | None = None,
) -> ExecutionRecord:
    return ExecutionRecord(
        task_id="t1",
        task_type=task_type,
        engine_used=engine,
        model_used=model,
        success=success,
        cost_usd=cost,
        duration_seconds=duration,
        error_message=error,
        created_at=created_at or datetime.now(),
    )


class TestInMemoryExecutionRecordRepository:
    def setup_method(self) -> None:
        self.repo = InMemoryExecutionRecordRepository()

    @pytest.mark.asyncio
    async def test_save_and_list_recent(self) -> None:
        await self.repo.save(_rec())
        await self.repo.save(_rec())
        records = await self.repo.list_recent()
        assert len(records) == 2

    @pytest.mark.asyncio
    async def test_list_recent_limit(self) -> None:
        for _ in range(5):
            await self.repo.save(_rec())
        records = await self.repo.list_recent(limit=3)
        assert len(records) == 3

    @pytest.mark.asyncio
    async def test_list_recent_ordered_by_created_at(self) -> None:
        old = _rec(created_at=datetime.now() - timedelta(hours=1))
        new = _rec(created_at=datetime.now())
        await self.repo.save(old)
        await self.repo.save(new)
        records = await self.repo.list_recent()
        assert records[0].created_at >= records[1].created_at

    @pytest.mark.asyncio
    async def test_list_by_task_type(self) -> None:
        await self.repo.save(_rec(task_type=TaskType.SIMPLE_QA))
        await self.repo.save(_rec(task_type=TaskType.CODE_GENERATION))
        await self.repo.save(_rec(task_type=TaskType.SIMPLE_QA))
        records = await self.repo.list_by_task_type(TaskType.SIMPLE_QA)
        assert len(records) == 2

    @pytest.mark.asyncio
    async def test_list_failures(self) -> None:
        await self.repo.save(_rec(success=True))
        await self.repo.save(_rec(success=False, error="err1"))
        await self.repo.save(_rec(success=False, error="err2"))
        failures = await self.repo.list_failures()
        assert len(failures) == 2

    @pytest.mark.asyncio
    async def test_list_failures_since(self) -> None:
        old = _rec(success=False, error="old", created_at=datetime.now() - timedelta(days=2))
        new = _rec(success=False, error="new", created_at=datetime.now())
        await self.repo.save(old)
        await self.repo.save(new)
        since = datetime.now() - timedelta(days=1)
        failures = await self.repo.list_failures(since=since)
        assert len(failures) == 1
        assert failures[0].error_message == "new"

    @pytest.mark.asyncio
    async def test_get_stats_empty(self) -> None:
        stats = await self.repo.get_stats()
        assert stats.total_count == 0
        assert stats.success_rate == 0.0

    @pytest.mark.asyncio
    async def test_get_stats_computed(self) -> None:
        await self.repo.save(_rec(success=True, cost=0.10, duration=5.0))
        await self.repo.save(_rec(success=True, cost=0.20, duration=10.0))
        await self.repo.save(_rec(success=False, cost=0.05, duration=2.0))
        stats = await self.repo.get_stats()
        assert stats.total_count == 3
        assert stats.success_count == 2
        assert stats.failure_count == 1
        assert stats.success_rate == pytest.approx(2 / 3)
        assert stats.avg_cost_usd == pytest.approx(0.35 / 3)

    @pytest.mark.asyncio
    async def test_get_stats_by_task_type(self) -> None:
        await self.repo.save(_rec(task_type=TaskType.SIMPLE_QA, success=True))
        await self.repo.save(_rec(task_type=TaskType.CODE_GENERATION, success=False))
        stats = await self.repo.get_stats(task_type=TaskType.SIMPLE_QA)
        assert stats.total_count == 1
        assert stats.success_count == 1

    @pytest.mark.asyncio
    async def test_get_stats_model_distribution(self) -> None:
        await self.repo.save(_rec(model="ollama/qwen3:8b"))
        await self.repo.save(_rec(model="ollama/qwen3:8b"))
        await self.repo.save(_rec(model="claude-sonnet-4-6"))
        stats = await self.repo.get_stats()
        assert stats.model_distribution["ollama/qwen3:8b"] == 2
        assert stats.model_distribution["claude-sonnet-4-6"] == 1

    @pytest.mark.asyncio
    async def test_get_stats_engine_distribution(self) -> None:
        await self.repo.save(_rec(engine=AgentEngineType.OLLAMA))
        await self.repo.save(_rec(engine=AgentEngineType.CLAUDE_CODE))
        stats = await self.repo.get_stats()
        assert stats.engine_distribution["ollama"] == 1
        assert stats.engine_distribution["claude_code"] == 1

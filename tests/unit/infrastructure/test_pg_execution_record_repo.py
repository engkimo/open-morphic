"""Tests for PgExecutionRecordRepository — Sprint 17.1.

Uses mock async sessions (no real DB in unit tests).
Follows the same _FakeSessionContext pattern as test_pg_fractal_learning_repo.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.entities.execution_record import ExecutionRecord
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from infrastructure.persistence.models import ExecutionRecordModel
from infrastructure.persistence.pg_execution_record_repository import (
    PgExecutionRecordRepository,
)

# ═══════════════════════════════════════════════════════════════
# Test helpers
# ═══════════════════════════════════════════════════════════════


class _FakeSessionContext:
    """Async context manager that returns the mock session."""

    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *args: object) -> None:
        pass


def _mock_session_factory() -> tuple[MagicMock, AsyncMock]:
    session = AsyncMock()
    # session.add() is synchronous in SQLAlchemy AsyncSession — use MagicMock
    # to avoid "coroutine never awaited" RuntimeWarning.
    session.add = MagicMock()
    factory = MagicMock()
    factory.return_value = _FakeSessionContext(session)
    return factory, session


def _sample_record(**overrides: object) -> ExecutionRecord:
    defaults = dict(
        task_id="task-001",
        task_type=TaskType.CODE_GENERATION,
        goal="implement fibonacci",
        engine_used=AgentEngineType.OLLAMA,
        model_used="ollama/qwen3:8b",
        success=True,
        cost_usd=0.0,
        duration_seconds=1.5,
        cache_hit_rate=0.8,
    )
    defaults.update(overrides)
    return ExecutionRecord(**defaults)


def _sample_model(**overrides: object) -> ExecutionRecordModel:
    defaults = dict(
        id=uuid.uuid4(),
        task_id="task-001",
        task_type="code_generation",
        goal="implement fibonacci",
        engine_used="ollama",
        model_used="ollama/qwen3:8b",
        success=True,
        error_message=None,
        cost_usd=Decimal("0.000000"),
        duration_seconds=1.5,
        cache_hit_rate=0.8,
        user_rating=None,
        created_at=datetime(2026, 3, 26),
    )
    defaults.update(overrides)
    return ExecutionRecordModel(**defaults)


# ═══════════════════════════════════════════════════════════════
# Mapping round-trip tests
# ═══════════════════════════════════════════════════════════════


class TestExecutionRecordMapping:
    def test_entity_to_model(self) -> None:
        record = _sample_record()
        model = PgExecutionRecordRepository._to_model(record)
        assert model.task_id == "task-001"
        assert model.task_type == "code_generation"
        assert model.engine_used == "ollama"
        assert model.model_used == "ollama/qwen3:8b"
        assert model.success is True
        assert model.cost_usd == Decimal("0.0")
        assert model.duration_seconds == 1.5
        assert model.cache_hit_rate == 0.8

    def test_model_to_entity(self) -> None:
        model = _sample_model()
        entity = PgExecutionRecordRepository._to_entity(model)
        assert entity.task_id == "task-001"
        assert entity.task_type == TaskType.CODE_GENERATION
        assert entity.engine_used == AgentEngineType.OLLAMA
        assert entity.model_used == "ollama/qwen3:8b"
        assert entity.success is True
        assert entity.cost_usd == pytest.approx(0.0)
        assert entity.duration_seconds == 1.5
        assert entity.cache_hit_rate == 0.8

    def test_round_trip_preserves_all_fields(self) -> None:
        record = _sample_record(
            success=False,
            error_message="timeout",
            cost_usd=0.05,
            user_rating=4.0,
        )
        model = PgExecutionRecordRepository._to_model(record)
        model.id = uuid.uuid4()
        restored = PgExecutionRecordRepository._to_entity(model)
        assert restored.task_id == record.task_id
        assert restored.task_type == record.task_type
        assert restored.engine_used == record.engine_used
        assert restored.success is False
        assert restored.error_message == "timeout"
        assert restored.cost_usd == pytest.approx(0.05)
        assert restored.user_rating == pytest.approx(4.0)


# ═══════════════════════════════════════════════════════════════
# save tests
# ═══════════════════════════════════════════════════════════════


class TestSaveExecutionRecord:
    @pytest.mark.asyncio
    async def test_save_adds_and_commits(self) -> None:
        factory, session = _mock_session_factory()
        repo = PgExecutionRecordRepository(factory)
        record = _sample_record()

        await repo.save(record)

        session.add.assert_called_once()
        session.commit.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════
# list_recent tests
# ═══════════════════════════════════════════════════════════════


class TestListRecent:
    @pytest.mark.asyncio
    async def test_returns_entities(self) -> None:
        factory, session = _mock_session_factory()
        model = _sample_model()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [model]
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgExecutionRecordRepository(factory)
        records = await repo.list_recent(limit=10)

        assert len(records) == 1
        assert records[0].task_id == "task-001"

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        factory, session = _mock_session_factory()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgExecutionRecordRepository(factory)
        records = await repo.list_recent()
        assert records == []


# ═══════════════════════════════════════════════════════════════
# list_by_task_type tests
# ═══════════════════════════════════════════════════════════════


class TestListByTaskType:
    @pytest.mark.asyncio
    async def test_filters_by_type(self) -> None:
        factory, session = _mock_session_factory()
        model = _sample_model(task_type="simple_qa")
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [model]
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgExecutionRecordRepository(factory)
        records = await repo.list_by_task_type(TaskType.SIMPLE_QA, limit=5)

        assert len(records) == 1
        session.execute.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════
# list_failures tests
# ═══════════════════════════════════════════════════════════════


class TestListFailures:
    @pytest.mark.asyncio
    async def test_list_failures_without_since(self) -> None:
        factory, session = _mock_session_factory()
        model = _sample_model(success=False, error_message="crash")
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [model]
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgExecutionRecordRepository(factory)
        failures = await repo.list_failures()

        assert len(failures) == 1
        assert failures[0].success is False

    @pytest.mark.asyncio
    async def test_list_failures_with_since(self) -> None:
        factory, session = _mock_session_factory()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgExecutionRecordRepository(factory)
        failures = await repo.list_failures(since=datetime(2026, 3, 25))

        assert failures == []
        session.execute.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════
# get_stats tests
# ═══════════════════════════════════════════════════════════════


class TestGetStats:
    @pytest.mark.asyncio
    async def test_empty_stats(self) -> None:
        factory, session = _mock_session_factory()
        # Aggregation returns zeros
        agg_row = MagicMock()
        agg_row.total = 0
        agg_row.success_count = 0
        agg_row.avg_cost = None
        agg_row.avg_duration = None
        agg_result = MagicMock()
        agg_result.one.return_value = agg_row
        session.execute = AsyncMock(return_value=agg_result)

        repo = PgExecutionRecordRepository(factory)
        stats = await repo.get_stats()

        assert stats.total_count == 0
        assert stats.success_rate == 0.0

    @pytest.mark.asyncio
    async def test_stats_with_data(self) -> None:
        factory, session = _mock_session_factory()
        # First call: aggregation
        agg_row = MagicMock()
        agg_row.total = 10
        agg_row.success_count = 8
        agg_row.avg_cost = Decimal("0.05")
        agg_row.avg_duration = 2.5
        agg_result = MagicMock()
        agg_result.one.return_value = agg_row

        # Second call: model distribution
        model_row = MagicMock()
        model_row.model_used = "ollama/qwen3:8b"
        model_row.cnt = 7
        model_result = MagicMock()
        model_result.__iter__ = lambda self: iter([model_row])

        # Third call: engine distribution
        engine_row = MagicMock()
        engine_row.engine_used = "ollama"
        engine_row.cnt = 10
        engine_result = MagicMock()
        engine_result.__iter__ = lambda self: iter([engine_row])

        session.execute = AsyncMock(side_effect=[agg_result, model_result, engine_result])

        repo = PgExecutionRecordRepository(factory)
        stats = await repo.get_stats()

        assert stats.total_count == 10
        assert stats.success_count == 8
        assert stats.failure_count == 2
        assert stats.avg_cost_usd == pytest.approx(0.05)
        assert stats.avg_duration_seconds == pytest.approx(2.5)
        assert stats.model_distribution == {"ollama/qwen3:8b": 7}
        assert stats.engine_distribution == {"ollama": 10}

    @pytest.mark.asyncio
    async def test_stats_filtered_by_task_type(self) -> None:
        factory, session = _mock_session_factory()
        agg_row = MagicMock()
        agg_row.total = 3
        agg_row.success_count = 3
        agg_row.avg_cost = Decimal("0.00")
        agg_row.avg_duration = 0.5
        agg_result = MagicMock()
        agg_result.one.return_value = agg_row

        model_result = MagicMock()
        model_result.__iter__ = lambda self: iter([])
        engine_result = MagicMock()
        engine_result.__iter__ = lambda self: iter([])

        session.execute = AsyncMock(side_effect=[agg_result, model_result, engine_result])

        repo = PgExecutionRecordRepository(factory)
        stats = await repo.get_stats(task_type=TaskType.SIMPLE_QA)

        assert stats.total_count == 3
        assert stats.success_rate == 1.0

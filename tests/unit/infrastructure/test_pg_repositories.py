"""Tests for PostgreSQL repository implementations — Sprint 2-A.

Uses mock async sessions (no real DB in unit tests).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.entities.cost import CostRecord
from domain.entities.memory import MemoryEntry
from domain.entities.task import SubTask, TaskEntity
from domain.value_objects.status import MemoryType, SubTaskStatus, TaskStatus
from infrastructure.persistence.models import MemoryModel, TaskModel
from infrastructure.persistence.pg_cost_repository import PgCostRepository
from infrastructure.persistence.pg_memory_repository import PgMemoryRepository
from infrastructure.persistence.pg_task_repository import PgTaskRepository

# ═══════════════════════════════════════════════════════════════
# Mapping tests — model <-> entity conversion
# ═══════════════════════════════════════════════════════════════


class TestPgTaskRepositoryMapping:
    def test_to_model_and_back(self) -> None:
        task = TaskEntity(
            goal="test goal",
            status=TaskStatus.RUNNING,
            subtasks=[
                SubTask(
                    description="step 1",
                    status=SubTaskStatus.SUCCESS,
                    result="done",
                    model_used="ollama/qwen3:8b",
                    cost_usd=0.0,
                ),
                SubTask(
                    description="step 2",
                    status=SubTaskStatus.PENDING,
                    dependencies=["step1_id"],
                ),
            ],
            total_cost_usd=0.05,
        )
        model = PgTaskRepository._to_model(task)
        assert model.goal == "test goal"
        assert model.status == "running"
        assert len(model.metadata_["subtasks"]) == 2

        roundtrip = PgTaskRepository._to_entity(model)
        assert roundtrip.goal == "test goal"
        assert roundtrip.status == TaskStatus.RUNNING
        assert len(roundtrip.subtasks) == 2
        assert roundtrip.subtasks[0].status == SubTaskStatus.SUCCESS
        assert roundtrip.subtasks[0].result == "done"
        assert roundtrip.total_cost_usd == 0.05

    def test_to_model_empty_subtasks(self) -> None:
        task = TaskEntity(goal="minimal task")
        model = PgTaskRepository._to_model(task)
        assert model.metadata_["subtasks"] == []

        entity = PgTaskRepository._to_entity(model)
        assert entity.subtasks == []

    def test_to_entity_missing_metadata(self) -> None:
        model = TaskModel(
            id=uuid.uuid4(),
            goal="legacy",
            status="pending",
            metadata_={},
            created_at=datetime.now(),
        )
        entity = PgTaskRepository._to_entity(model)
        assert entity.subtasks == []
        assert entity.total_cost_usd == 0.0


class TestPgCostRepositoryMapping:
    def test_to_model_and_back(self) -> None:
        record = CostRecord(
            model="claude-sonnet-4-6",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.05,
            cached_tokens=20,
            is_local=False,
        )
        model = PgCostRepository._to_model(record)
        assert model.model == "claude-sonnet-4-6"
        assert model.cost_usd == Decimal("0.05")
        assert model.is_local is False

        roundtrip = PgCostRepository._to_entity(model)
        assert roundtrip.model == "claude-sonnet-4-6"
        assert roundtrip.cost_usd == 0.05
        assert roundtrip.is_local is False

    def test_local_model_zero_cost(self) -> None:
        record = CostRecord(model="ollama/qwen3:8b", cost_usd=0.0, is_local=True)
        model = PgCostRepository._to_model(record)
        assert model.is_local is True
        assert model.cost_usd == Decimal("0")


class TestPgMemoryRepositoryMapping:
    def test_to_model_and_back(self) -> None:
        entry = MemoryEntry(
            content="important fact",
            memory_type=MemoryType.L2_SEMANTIC,
            importance_score=0.9,
            access_count=3,
            metadata={"key": "value"},
        )
        model = PgMemoryRepository._to_model(entry)
        assert model.content == "important fact"
        assert model.memory_type == "l2_semantic"
        assert model.importance_score == 0.9

        roundtrip = PgMemoryRepository._to_entity(model)
        assert roundtrip.content == "important fact"
        assert roundtrip.memory_type == MemoryType.L2_SEMANTIC
        assert roundtrip.importance_score == 0.9
        assert roundtrip.access_count == 3

    def test_to_entity_empty_metadata(self) -> None:
        model = MemoryModel(
            id=uuid.uuid4(),
            content="test",
            memory_type="l1_active",
            access_count=1,
            importance_score=0.5,
            metadata_=None,
            created_at=datetime.now(),
            last_accessed=datetime.now(),
        )
        entity = PgMemoryRepository._to_entity(model)
        assert entity.metadata == {}


# ═══════════════════════════════════════════════════════════════
# Container PG/InMemory switching
# ═══════════════════════════════════════════════════════════════


class TestContainerRepoSwitch:
    def test_default_uses_in_memory(self) -> None:
        from infrastructure.persistence.in_memory import InMemoryTaskRepository
        from interface.api.container import AppContainer
        from shared.config import Settings

        s = Settings(use_postgres=False)
        c = AppContainer(settings=s)
        assert isinstance(c.task_repo, InMemoryTaskRepository)

    def test_use_postgres_flag_creates_pg_repos(self) -> None:
        from interface.api.container import AppContainer
        from shared.config import Settings

        s = Settings(use_postgres=True)
        c = AppContainer(settings=s)
        assert type(c.task_repo).__name__ == "PgTaskRepository"
        assert type(c.cost_repo).__name__ == "PgCostRepository"
        assert type(c.memory_repo).__name__ == "PgMemoryRepository"


# ═══════════════════════════════════════════════════════════════
# PgTaskRepository async operations (mocked session)
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
    """Return (factory, session) pair. factory() returns async CM yielding session."""
    session = AsyncMock()
    # session.add() is synchronous in SQLAlchemy AsyncSession — use MagicMock
    # to avoid "coroutine never awaited" RuntimeWarning.
    session.add = MagicMock()
    factory = MagicMock()
    factory.return_value = _FakeSessionContext(session)
    return factory, session


class TestPgTaskRepositorySave:
    @pytest.mark.asyncio
    async def test_save_adds_model(self) -> None:
        factory, session = _mock_session_factory()
        repo = PgTaskRepository(factory)
        task = TaskEntity(goal="save test")
        await repo.save(task)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self) -> None:
        factory, session = _mock_session_factory()
        session.get = AsyncMock(return_value=None)
        repo = PgTaskRepository(factory)
        result = await repo.get_by_id(str(uuid.uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_invalid_uuid(self) -> None:
        factory, session = _mock_session_factory()
        repo = PgTaskRepository(factory)
        result = await repo.get_by_id("not-a-uuid")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_calls_session_delete(self) -> None:
        factory, session = _mock_session_factory()
        uid = uuid.uuid4()
        mock_model = MagicMock()
        session.get = AsyncMock(return_value=mock_model)
        # Mock plan cascade query — returns empty scalars
        mock_scalars = MagicMock()
        mock_scalars.__iter__ = MagicMock(return_value=iter([]))
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)
        repo = PgTaskRepository(factory)
        await repo.delete(str(uid))
        session.delete.assert_awaited_once_with(mock_model)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_is_noop(self) -> None:
        factory, session = _mock_session_factory()
        session.get = AsyncMock(return_value=None)
        # Mock plan cascade query — returns empty scalars
        mock_scalars = MagicMock()
        mock_scalars.__iter__ = MagicMock(return_value=iter([]))
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)
        repo = PgTaskRepository(factory)
        await repo.delete(str(uuid.uuid4()))
        session.delete.assert_not_awaited()


class TestPgCostRepositorySave:
    @pytest.mark.asyncio
    async def test_save_adds_model(self) -> None:
        factory, session = _mock_session_factory()
        repo = PgCostRepository(factory)
        record = CostRecord(model="test-model", cost_usd=0.01)
        await repo.save(record)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()


class TestPgMemoryRepositoryAdd:
    @pytest.mark.asyncio
    async def test_add_entry(self) -> None:
        factory, session = _mock_session_factory()
        repo = PgMemoryRepository(factory)
        entry = MemoryEntry(content="test memory", memory_type=MemoryType.L1_ACTIVE)
        await repo.add(entry)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self) -> None:
        factory, session = _mock_session_factory()
        session.get = AsyncMock(return_value=None)
        repo = PgMemoryRepository(factory)
        result = await repo.get_by_id(str(uuid.uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_invalid_uuid(self) -> None:
        factory, session = _mock_session_factory()
        repo = PgMemoryRepository(factory)
        result = await repo.get_by_id("bad-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_entry(self) -> None:
        factory, session = _mock_session_factory()
        mock_model = MagicMock()
        session.get = AsyncMock(return_value=mock_model)
        repo = PgMemoryRepository(factory)
        await repo.delete(str(uuid.uuid4()))
        session.delete.assert_awaited_once_with(mock_model)

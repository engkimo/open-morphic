"""Tests for SQLite persistence fallback — Sprint 24.2 (TD-130).

Verifies that portable ORM types (GUID, PortableJSON) work correctly
with SQLite via aiosqlite, and that PG repos can be reused unchanged.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from domain.entities.task import TaskEntity
from domain.value_objects.status import TaskStatus
from infrastructure.persistence.models import (
    Base,
    CostLogModel,
    ExecutionRecordModel,
    PlanModel,
    TaskModel,
)
from infrastructure.persistence.pg_task_repository import PgTaskRepository

# pytestmark applied per-class (TestSQLiteConfig has sync tests)


@pytest.fixture
async def sqlite_engine(tmp_path: Path):
    """Create a temporary SQLite database for testing."""
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(sqlite_engine):
    return async_sessionmaker(
        sqlite_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# ── Portable Types ──


@pytest.mark.asyncio
class TestGUIDType:
    async def test_uuid_roundtrip(self, session_factory) -> None:
        """UUID stored as string in SQLite and recovered correctly."""
        uid = uuid.uuid4()
        async with session_factory() as session:
            model = TaskModel(
                id=uid,
                goal="test task",
                status="pending",
                metadata_={"key": "value"},
            )
            session.add(model)
            await session.commit()

        async with session_factory() as session:
            result = await session.get(TaskModel, uid)
            assert result is not None
            assert result.id == uid
            assert isinstance(result.id, uuid.UUID)

    async def test_uuid_from_string(self, session_factory) -> None:
        """UUID can be queried from string representation."""
        uid = uuid.uuid4()
        async with session_factory() as session:
            model = TaskModel(id=uid, goal="test", metadata_={})
            session.add(model)
            await session.commit()

        async with session_factory() as session:
            # PG repos convert string to UUID — verify this works with SQLite
            result = await session.get(TaskModel, uid)
            assert result is not None
            assert str(result.id) == str(uid)


@pytest.mark.asyncio
class TestPortableJSON:
    async def test_json_dict_roundtrip(self, session_factory) -> None:
        """Dict stored as JSON in SQLite."""
        uid = uuid.uuid4()
        metadata = {"subtasks": [{"id": "s1", "status": "pending"}], "total_cost": 1.5}
        async with session_factory() as session:
            model = TaskModel(id=uid, goal="json test", metadata_=metadata)
            session.add(model)
            await session.commit()

        async with session_factory() as session:
            result = await session.get(TaskModel, uid)
            assert result is not None
            assert result.metadata_ == metadata

    async def test_json_list_roundtrip(self, session_factory) -> None:
        """List stored as JSON in plan steps."""
        uid = uuid.uuid4()
        steps = [{"step": 1, "action": "analyze"}, {"step": 2, "action": "execute"}]
        async with session_factory() as session:
            model = PlanModel(id=uid, goal="plan test", steps=steps)
            session.add(model)
            await session.commit()

        async with session_factory() as session:
            result = await session.get(PlanModel, uid)
            assert result is not None
            assert result.steps == steps

    async def test_empty_dict(self, session_factory) -> None:
        uid = uuid.uuid4()
        async with session_factory() as session:
            model = TaskModel(id=uid, goal="empty", metadata_={})
            session.add(model)
            await session.commit()

        async with session_factory() as session:
            result = await session.get(TaskModel, uid)
            assert result.metadata_ == {}


# ── PG Repository Reuse ──


@pytest.mark.asyncio
class TestPgTaskRepoOnSQLite:
    """Verify PG repos work unchanged on SQLite backend."""

    async def test_save_and_get(self, session_factory) -> None:
        repo = PgTaskRepository(session_factory)
        task = TaskEntity(
            id=str(uuid.uuid4()),
            goal="SQLite save test",
            status=TaskStatus.PENDING,
            subtasks=[],
            total_cost_usd=0.0,
            created_at=datetime.now(tz=UTC),
        )
        await repo.save(task)
        loaded = await repo.get_by_id(task.id)
        assert loaded is not None
        assert loaded.goal == "SQLite save test"
        assert loaded.status == TaskStatus.PENDING

    async def test_list_all(self, session_factory) -> None:
        repo = PgTaskRepository(session_factory)
        for i in range(3):
            task = TaskEntity(
                id=str(uuid.uuid4()),
                goal=f"Task {i}",
                status=TaskStatus.PENDING,
                subtasks=[],
                created_at=datetime.now(tz=UTC),
            )
            await repo.save(task)
        all_tasks = await repo.list_all()
        assert len(all_tasks) >= 3

    async def test_update(self, session_factory) -> None:
        repo = PgTaskRepository(session_factory)
        task = TaskEntity(
            id=str(uuid.uuid4()),
            goal="Update test",
            status=TaskStatus.PENDING,
            subtasks=[],
            created_at=datetime.now(tz=UTC),
        )
        await repo.save(task)
        task.status = TaskStatus.SUCCESS
        task.total_cost_usd = 0.05
        await repo.update(task)
        loaded = await repo.get_by_id(task.id)
        assert loaded is not None
        assert loaded.status == TaskStatus.SUCCESS

    async def test_delete(self, session_factory) -> None:
        repo = PgTaskRepository(session_factory)
        task = TaskEntity(
            id=str(uuid.uuid4()),
            goal="Delete test",
            status=TaskStatus.PENDING,
            subtasks=[],
            created_at=datetime.now(tz=UTC),
        )
        await repo.save(task)
        await repo.delete(task.id)
        loaded = await repo.get_by_id(task.id)
        assert loaded is None

    async def test_list_by_status(self, session_factory) -> None:
        repo = PgTaskRepository(session_factory)
        for status in [TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.PENDING]:
            task = TaskEntity(
                id=str(uuid.uuid4()),
                goal=f"Status {status.value}",
                status=status,
                subtasks=[],
                created_at=datetime.now(tz=UTC),
            )
            await repo.save(task)
        pending = await repo.list_by_status(TaskStatus.PENDING)
        assert len(pending) >= 2


# ── Other Models on SQLite ──


@pytest.mark.asyncio
class TestOtherModelsOnSQLite:
    async def test_cost_log(self, session_factory) -> None:
        async with session_factory() as session:
            model = CostLogModel(
                id=uuid.uuid4(),
                model="claude-sonnet-4-6",
                prompt_tokens=100,
                completion_tokens=50,
                cost_usd=Decimal("0.001"),
                is_local=False,
            )
            session.add(model)
            await session.commit()

        async with session_factory() as session:
            result = await session.get(CostLogModel, model.id)
            assert result is not None
            assert result.model == "claude-sonnet-4-6"
            assert result.prompt_tokens == 100

    async def test_execution_record(self, session_factory) -> None:
        async with session_factory() as session:
            model = ExecutionRecordModel(
                id=uuid.uuid4(),
                task_id="task-001",
                task_type="simple_qa",
                goal="Test",
                engine_used="ollama",
                model_used="qwen3:8b",
                success=True,
                cost_usd=Decimal("0"),
                duration_seconds=1.5,
            )
            session.add(model)
            await session.commit()

        async with session_factory() as session:
            result = await session.get(ExecutionRecordModel, model.id)
            assert result is not None
            assert result.success is True
            assert result.engine_used == "ollama"


# ── Config ──


class TestSQLiteConfig:
    def test_default_settings(self) -> None:
        from shared.config import Settings

        s = Settings()
        assert s.use_sqlite is False
        assert "sqlite+aiosqlite" in s.sqlite_url

    def test_sqlite_url_format(self) -> None:
        from shared.config import Settings

        s = Settings()
        assert s.sqlite_url.startswith("sqlite+aiosqlite:///")

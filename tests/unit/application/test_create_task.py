"""Tests for CreateTaskUseCase — goal decomposition and persistence."""

from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from application.use_cases.create_task import CreateTaskUseCase
from domain.entities.task import SubTask
from domain.ports.task_engine import TaskEngine
from domain.ports.task_repository import TaskRepository
from domain.value_objects.status import TaskStatus


@pytest.fixture
def engine() -> AsyncMock:
    return AsyncMock(spec=TaskEngine)


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock(spec=TaskRepository)


@pytest.fixture
def use_case(engine: AsyncMock, repo: AsyncMock) -> CreateTaskUseCase:
    return CreateTaskUseCase(engine, repo)


class TestCreateTask:
    async def test_creates_task_with_subtasks(
        self, use_case: CreateTaskUseCase, engine: AsyncMock
    ) -> None:
        engine.decompose.return_value = [
            SubTask(description="Step 1"),
            SubTask(description="Step 2"),
        ]
        task = await use_case.execute("Build fibonacci")

        assert task.goal == "Build fibonacci"
        assert len(task.subtasks) == 2

    async def test_saves_to_repository(
        self, use_case: CreateTaskUseCase, engine: AsyncMock, repo: AsyncMock
    ) -> None:
        engine.decompose.return_value = [SubTask(description="Step 1")]
        task = await use_case.execute("Test goal")

        repo.save.assert_awaited_once()
        saved_task = repo.save.call_args[0][0]
        assert saved_task.id == task.id

    async def test_task_has_pending_status(
        self, use_case: CreateTaskUseCase, engine: AsyncMock
    ) -> None:
        engine.decompose.return_value = [SubTask(description="Step 1")]
        task = await use_case.execute("Simple task")

        assert task.status == TaskStatus.PENDING

    async def test_empty_goal_raises_validation_error(
        self, use_case: CreateTaskUseCase, engine: AsyncMock
    ) -> None:
        engine.decompose.return_value = []
        with pytest.raises(ValidationError):
            await use_case.execute("")

    async def test_preserves_subtask_dependencies(
        self, use_case: CreateTaskUseCase, engine: AsyncMock
    ) -> None:
        s1 = SubTask(description="Write code")
        s2 = SubTask(description="Test code", dependencies=[s1.id])
        engine.decompose.return_value = [s1, s2]

        task = await use_case.execute("Code and test")

        assert task.subtasks[1].dependencies == [s1.id]

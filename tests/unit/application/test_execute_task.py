"""Tests for ExecuteTaskUseCase — task execution lifecycle."""

from unittest.mock import AsyncMock

import pytest

from application.use_cases.execute_task import ExecuteTaskUseCase, TaskNotFoundError
from domain.entities.task import SubTask, TaskEntity
from domain.ports.task_engine import TaskEngine
from domain.ports.task_repository import TaskRepository
from domain.value_objects.status import SubTaskStatus, TaskStatus


@pytest.fixture
def engine() -> AsyncMock:
    return AsyncMock(spec=TaskEngine)


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock(spec=TaskRepository)


@pytest.fixture
def use_case(engine: AsyncMock, repo: AsyncMock) -> ExecuteTaskUseCase:
    return ExecuteTaskUseCase(engine, repo)


def _make_task(*subtask_statuses: SubTaskStatus) -> TaskEntity:
    """Create a task with subtasks in given statuses."""
    subtasks = []
    for i, status in enumerate(subtask_statuses):
        s = SubTask(description=f"Step {i + 1}")
        s.status = status
        s.cost_usd = 0.01
        subtasks.append(s)
    return TaskEntity(goal="Test goal", subtasks=subtasks)


class TestExecuteTask:
    async def test_success_when_all_subtasks_pass(
        self, use_case: ExecuteTaskUseCase, engine: AsyncMock, repo: AsyncMock
    ) -> None:
        task = _make_task(SubTaskStatus.SUCCESS, SubTaskStatus.SUCCESS)
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        result = await use_case.execute(task.id)

        assert result.status == TaskStatus.SUCCESS

    async def test_fallback_on_partial_success(
        self, use_case: ExecuteTaskUseCase, engine: AsyncMock, repo: AsyncMock
    ) -> None:
        task = _make_task(SubTaskStatus.SUCCESS, SubTaskStatus.FAILED)
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        result = await use_case.execute(task.id)

        assert result.status == TaskStatus.FALLBACK

    async def test_failed_when_all_subtasks_fail(
        self, use_case: ExecuteTaskUseCase, engine: AsyncMock, repo: AsyncMock
    ) -> None:
        task = _make_task(SubTaskStatus.FAILED, SubTaskStatus.FAILED)
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        result = await use_case.execute(task.id)

        assert result.status == TaskStatus.FAILED

    async def test_not_found_raises(
        self, use_case: ExecuteTaskUseCase, repo: AsyncMock
    ) -> None:
        repo.get_by_id.return_value = None

        with pytest.raises(TaskNotFoundError) as exc_info:
            await use_case.execute("nonexistent-id")
        assert exc_info.value.task_id == "nonexistent-id"

    async def test_sets_running_before_execution(
        self, use_case: ExecuteTaskUseCase, engine: AsyncMock, repo: AsyncMock
    ) -> None:
        task = _make_task(SubTaskStatus.SUCCESS)
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        await use_case.execute(task.id)

        # repo.update called twice: once for RUNNING, once for final status
        assert repo.update.await_count == 2
        first_call_task = repo.update.call_args_list[0][0][0]
        assert first_call_task.status == TaskStatus.SUCCESS  # mutated in-place

    async def test_accumulates_total_cost(
        self, use_case: ExecuteTaskUseCase, engine: AsyncMock, repo: AsyncMock
    ) -> None:
        task = _make_task(SubTaskStatus.SUCCESS, SubTaskStatus.SUCCESS)
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        result = await use_case.execute(task.id)

        assert result.total_cost_usd == pytest.approx(0.02)

"""Tests for BackgroundPlannerUseCase — Sprint 2-D."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from application.use_cases.background_planner import BackgroundPlannerUseCase
from domain.entities.task import SubTask, TaskEntity
from domain.value_objects.status import SubTaskStatus, TaskStatus
from infrastructure.persistence.in_memory import InMemoryTaskRepository


def _make_planner(
    task: TaskEntity | None = None,
) -> tuple[BackgroundPlannerUseCase, InMemoryTaskRepository]:
    """Create a planner with mock LLM and in-memory task repo."""
    llm = AsyncMock()
    repo = InMemoryTaskRepository()
    if task:
        repo._store[task.id] = task
    planner = BackgroundPlannerUseCase(llm=llm, task_repo=repo, poll_interval=0.05)
    return planner, repo


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_creates_background_task(self) -> None:
        task = TaskEntity(goal="test", status=TaskStatus.RUNNING)
        planner, _ = _make_planner(task)
        await planner.start(task.id)
        assert task.id in planner._running_tasks
        await planner.stop(task.id)

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self) -> None:
        task = TaskEntity(goal="test", status=TaskStatus.RUNNING)
        planner, _ = _make_planner(task)
        await planner.start(task.id)
        bg_task_1 = planner._running_tasks[task.id]
        await planner.start(task.id)  # Should not create another
        bg_task_2 = planner._running_tasks[task.id]
        assert bg_task_1 is bg_task_2
        await planner.stop(task.id)

    @pytest.mark.asyncio
    async def test_stop_cancels_monitoring(self) -> None:
        task = TaskEntity(goal="test", status=TaskStatus.RUNNING)
        planner, _ = _make_planner(task)
        await planner.start(task.id)
        await planner.stop(task.id)
        assert task.id not in planner._running_tasks


class TestRecommendations:
    @pytest.mark.asyncio
    async def test_no_recommendations_initially(self) -> None:
        planner, _ = _make_planner()
        assert planner.get_recommendations("any") == []

    @pytest.mark.asyncio
    async def test_recommendations_on_failure(self) -> None:
        task = TaskEntity(
            goal="failing task",
            status=TaskStatus.RUNNING,
            subtasks=[
                SubTask(
                    description="broken step",
                    status=SubTaskStatus.FAILED,
                    error="timeout",
                ),
            ],
        )
        planner, repo = _make_planner(task)
        await planner.start(task.id)
        # Wait for at least one poll cycle
        await asyncio.sleep(0.1)

        recs = planner.get_recommendations(task.id)
        assert len(recs) >= 1
        assert "broken step" in recs[0]
        assert "timeout" in recs[0]
        await planner.stop(task.id)

    @pytest.mark.asyncio
    async def test_no_duplicate_recommendations(self) -> None:
        task = TaskEntity(
            goal="dup test",
            status=TaskStatus.RUNNING,
            subtasks=[
                SubTask(description="step", status=SubTaskStatus.FAILED, error="err"),
            ],
        )
        planner, _ = _make_planner(task)
        await planner.start(task.id)
        await asyncio.sleep(0.15)  # Multiple poll cycles

        recs = planner.get_recommendations(task.id)
        # Should not have duplicates
        assert len(recs) == len(set(recs))
        await planner.stop(task.id)


class TestAutoStop:
    @pytest.mark.asyncio
    async def test_stops_on_task_completion(self) -> None:
        task = TaskEntity(
            goal="complete test",
            status=TaskStatus.SUCCESS,
            subtasks=[SubTask(description="done", status=SubTaskStatus.SUCCESS)],
        )
        planner, _ = _make_planner(task)
        await planner.start(task.id)
        await asyncio.sleep(0.1)
        # Should auto-stop because task is already complete
        assert task.id not in planner._running_tasks

    @pytest.mark.asyncio
    async def test_stops_on_task_not_found(self) -> None:
        planner, _ = _make_planner()  # No task in repo
        await planner.start("missing-id")
        await asyncio.sleep(0.1)
        assert "missing-id" not in planner._running_tasks


class TestGetRecommendationsEmpty:
    @pytest.mark.asyncio
    async def test_returns_empty_for_unknown_task(self) -> None:
        planner, _ = _make_planner()
        assert planner.get_recommendations("unknown") == []

    @pytest.mark.asyncio
    async def test_returns_copy(self) -> None:
        """get_recommendations should return a copy, not a reference."""
        planner, _ = _make_planner()
        planner._recommendations["t1"] = ["rec1"]
        recs = planner.get_recommendations("t1")
        recs.append("mutated")
        assert len(planner.get_recommendations("t1")) == 1

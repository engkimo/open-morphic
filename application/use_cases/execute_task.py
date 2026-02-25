"""ExecuteTaskUseCase — load, execute, and persist a task."""

from __future__ import annotations

from domain.entities.task import TaskEntity
from domain.ports.task_engine import TaskEngine
from domain.ports.task_repository import TaskRepository
from domain.value_objects.status import TaskStatus


class TaskNotFoundError(Exception):
    def __init__(self, task_id: str) -> None:
        super().__init__(f"Task not found: {task_id}")
        self.task_id = task_id


class ExecuteTaskUseCase:
    def __init__(self, engine: TaskEngine, repo: TaskRepository) -> None:
        self._engine = engine
        self._repo = repo

    async def execute(self, task_id: str) -> TaskEntity:
        """Load task, run through engine, update final status, and persist."""
        task = await self._repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)

        task.status = TaskStatus.RUNNING
        await self._repo.update(task)

        result = await self._engine.execute(task)

        # Determine final status from subtask outcomes
        if result.success_rate == 1.0:
            result.status = TaskStatus.SUCCESS
        elif result.success_rate > 0:
            result.status = TaskStatus.FALLBACK
        else:
            result.status = TaskStatus.FAILED

        result.total_cost_usd = sum(s.cost_usd for s in result.subtasks)
        await self._repo.update(result)
        return result

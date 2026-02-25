"""CreateTaskUseCase — decompose a goal into subtasks and persist."""

from __future__ import annotations

from domain.entities.task import TaskEntity
from domain.ports.task_engine import TaskEngine
from domain.ports.task_repository import TaskRepository


class CreateTaskUseCase:
    def __init__(self, engine: TaskEngine, repo: TaskRepository) -> None:
        self._engine = engine
        self._repo = repo

    async def execute(self, goal: str) -> TaskEntity:
        """Decompose goal into subtasks, create task, and persist."""
        subtasks = await self._engine.decompose(goal)
        task = TaskEntity(goal=goal, subtasks=subtasks)
        await self._repo.save(task)
        return task

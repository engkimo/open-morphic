"""TaskEngine port — abstraction over task decomposition and execution."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.task import SubTask, TaskEntity


class TaskEngine(ABC):
    @abstractmethod
    async def decompose(self, goal: str) -> list[SubTask]:
        """Analyze intent and decompose goal into subtasks."""
        ...

    @abstractmethod
    async def execute(self, task: TaskEntity) -> TaskEntity:
        """Execute all subtasks in the task DAG, returning updated entity."""
        ...

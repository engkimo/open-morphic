"""TaskRepository port — persistence abstraction for tasks."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.task import TaskEntity
from domain.value_objects.status import TaskStatus


class TaskRepository(ABC):
    @abstractmethod
    async def save(self, task: TaskEntity) -> None: ...

    @abstractmethod
    async def get_by_id(self, task_id: str) -> TaskEntity | None: ...

    @abstractmethod
    async def list_by_status(self, status: TaskStatus) -> list[TaskEntity]: ...

    @abstractmethod
    async def update(self, task: TaskEntity) -> None: ...

    @abstractmethod
    async def list_all(self) -> list[TaskEntity]: ...

    @abstractmethod
    async def delete(self, task_id: str) -> None: ...

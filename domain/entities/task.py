"""Task entity — core of the Task Graph Engine. Pure domain, no ORM."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects.status import SubTaskStatus, TaskStatus


class SubTask(BaseModel):
    """A node in the task DAG."""

    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = Field(min_length=1)
    status: SubTaskStatus = SubTaskStatus.PENDING
    dependencies: list[str] = Field(default_factory=list)
    result: str | None = None
    error: str | None = None
    model_used: str | None = None
    cost_usd: float = Field(default=0.0, ge=0.0)


class TaskEntity(BaseModel):
    """Top-level goal with subtask decomposition."""

    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str = Field(min_length=1)
    status: TaskStatus = TaskStatus.PENDING
    subtasks: list[SubTask] = Field(default_factory=list)
    total_cost_usd: float = Field(default=0.0, ge=0.0)
    created_at: datetime = Field(default_factory=datetime.now)

    def get_ready_subtasks(self) -> list[SubTask]:
        """Return subtasks whose dependencies are all completed."""
        completed_ids = {
            t.id for t in self.subtasks if t.status == SubTaskStatus.SUCCESS
        }
        return [
            t
            for t in self.subtasks
            if t.status == SubTaskStatus.PENDING
            and all(d in completed_ids for d in t.dependencies)
        ]

    def mark_subtask(
        self,
        subtask_id: str,
        status: SubTaskStatus,
        result: str | None = None,
    ) -> None:
        """Update a subtask's status."""
        for t in self.subtasks:
            if t.id == subtask_id:
                t.status = status
                t.result = result
                break

    @property
    def is_complete(self) -> bool:
        return all(
            t.status in (SubTaskStatus.SUCCESS, SubTaskStatus.FAILED)
            for t in self.subtasks
        )

    @property
    def success_rate(self) -> float:
        if not self.subtasks:
            return 0.0
        succeeded = sum(
            1 for t in self.subtasks if t.status == SubTaskStatus.SUCCESS
        )
        return succeeded / len(self.subtasks)

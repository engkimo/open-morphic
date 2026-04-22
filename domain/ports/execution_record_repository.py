"""ExecutionRecordRepository port — storage for execution history.

Domain defines WHAT it needs. Infrastructure provides HOW.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from domain.entities.execution_record import ExecutionRecord
from domain.value_objects.model_tier import TaskType


@dataclass
class ExecutionStats:
    """Aggregated execution statistics."""

    total_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_cost_usd: float = 0.0
    avg_duration_seconds: float = 0.0
    model_distribution: dict[str, int] = field(default_factory=dict)
    engine_distribution: dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.total_count == 0:
            return 0.0
        return self.success_count / self.total_count


class ExecutionRecordRepository(ABC):
    """Port for storing and querying execution records."""

    @abstractmethod
    async def save(self, record: ExecutionRecord) -> None:
        """Persist an execution record."""
        ...

    @abstractmethod
    async def list_recent(self, limit: int = 100) -> list[ExecutionRecord]:
        """List most recent execution records."""
        ...

    @abstractmethod
    async def list_by_task_type(
        self, task_type: TaskType, limit: int = 50
    ) -> list[ExecutionRecord]:
        """List records filtered by task type."""
        ...

    @abstractmethod
    async def list_failures(self, since: datetime | None = None) -> list[ExecutionRecord]:
        """List failed execution records, optionally since a given time."""
        ...

    @abstractmethod
    async def get_stats(self, task_type: TaskType | None = None) -> ExecutionStats:
        """Compute aggregated statistics, optionally for a specific task type."""
        ...

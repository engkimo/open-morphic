"""In-memory ExecutionRecordRepository — list-backed for dev and testing."""

from __future__ import annotations

from datetime import datetime

from domain.entities.execution_record import ExecutionRecord
from domain.ports.execution_record_repository import (
    ExecutionRecordRepository,
    ExecutionStats,
)
from domain.value_objects.model_tier import TaskType


class InMemoryExecutionRecordRepository(ExecutionRecordRepository):
    """List-backed ExecutionRecordRepository."""

    def __init__(self) -> None:
        self._records: list[ExecutionRecord] = []

    async def save(self, record: ExecutionRecord) -> None:
        self._records.append(record)

    async def list_recent(self, limit: int = 100) -> list[ExecutionRecord]:
        return sorted(self._records, key=lambda r: r.created_at, reverse=True)[:limit]

    async def list_by_task_type(
        self, task_type: TaskType, limit: int = 50
    ) -> list[ExecutionRecord]:
        filtered = [r for r in self._records if r.task_type == task_type]
        return sorted(filtered, key=lambda r: r.created_at, reverse=True)[:limit]

    async def list_failures(self, since: datetime | None = None) -> list[ExecutionRecord]:
        failures = [r for r in self._records if not r.success]
        if since is not None:
            failures = [r for r in failures if r.created_at >= since]
        return sorted(failures, key=lambda r: r.created_at, reverse=True)

    async def get_stats(self, task_type: TaskType | None = None) -> ExecutionStats:
        records = self._records
        if task_type is not None:
            records = [r for r in records if r.task_type == task_type]

        if not records:
            return ExecutionStats()

        success_count = sum(1 for r in records if r.success)
        total_cost = sum(r.cost_usd for r in records)
        total_duration = sum(r.duration_seconds for r in records)
        n = len(records)

        model_dist: dict[str, int] = {}
        engine_dist: dict[str, int] = {}
        for r in records:
            if r.model_used:
                model_dist[r.model_used] = model_dist.get(r.model_used, 0) + 1
            engine_dist[r.engine_used.value] = engine_dist.get(r.engine_used.value, 0) + 1

        return ExecutionStats(
            total_count=n,
            success_count=success_count,
            failure_count=n - success_count,
            avg_cost_usd=total_cost / n,
            avg_duration_seconds=total_duration / n,
            model_distribution=model_dist,
            engine_distribution=engine_dist,
        )

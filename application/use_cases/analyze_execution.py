"""AnalyzeExecutionUseCase — record execution outcomes and compute stats."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from domain.entities.execution_record import ExecutionRecord
from domain.ports.execution_record_repository import (
    ExecutionRecordRepository,
    ExecutionStats,
)
from domain.value_objects.model_tier import TaskType


@dataclass
class FailurePattern:
    """A recurring failure pattern extracted from execution history."""

    error_pattern: str
    count: int = 0
    task_types: list[str] = field(default_factory=list)
    engines: list[str] = field(default_factory=list)


class AnalyzeExecutionUseCase:
    """Record execution outcomes and analyze patterns."""

    def __init__(self, repo: ExecutionRecordRepository) -> None:
        self._repo = repo

    async def record(self, record: ExecutionRecord) -> None:
        """Save an execution record."""
        await self._repo.save(record)

    async def get_stats(self, task_type: TaskType | None = None) -> ExecutionStats:
        """Get aggregated execution statistics."""
        return await self._repo.get_stats(task_type)

    async def get_failure_patterns(self, limit: int = 50) -> list[FailurePattern]:
        """Analyze recent failures for recurring patterns.

        Groups failures by their first error line and returns the most common.
        """
        failures = await self._repo.list_failures()
        if not failures:
            return []

        # Group by first line of error message
        groups: dict[str, list[ExecutionRecord]] = {}
        for f in failures:
            key = self._normalize_error(f.error_message or "unknown")
            groups.setdefault(key, []).append(f)

        patterns: list[FailurePattern] = []
        for error_key, records in groups.items():
            task_types = list({r.task_type.value for r in records})
            engines = list({r.engine_used.value for r in records})
            patterns.append(
                FailurePattern(
                    error_pattern=error_key,
                    count=len(records),
                    task_types=task_types,
                    engines=engines,
                )
            )

        # Sort by count descending
        patterns.sort(key=lambda p: p.count, reverse=True)
        return patterns[:limit]

    async def get_model_distribution(self) -> dict[str, int]:
        """Get model usage distribution across all records."""
        records = await self._repo.list_recent(limit=1000)
        counter: Counter[str] = Counter()
        for r in records:
            if r.model_used:
                counter[r.model_used] += 1
        return dict(counter.most_common())

    @staticmethod
    def _normalize_error(error_message: str) -> str:
        """Normalize error message to group similar errors."""
        first_line = error_message.strip().split("\n")[0]
        # Truncate long messages
        if len(first_line) > 80:
            first_line = first_line[:80]
        return first_line

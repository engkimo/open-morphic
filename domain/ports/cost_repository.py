"""CostRepository port — persistence abstraction for cost tracking."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.cost import CostRecord


class CostRepository(ABC):
    @abstractmethod
    async def save(self, record: CostRecord) -> None: ...

    @abstractmethod
    async def get_daily_total(self) -> float: ...

    @abstractmethod
    async def get_monthly_total(self) -> float: ...

    @abstractmethod
    async def get_local_usage_rate(self) -> float: ...

    @abstractmethod
    async def list_recent(self, limit: int = 50) -> list[CostRecord]: ...

    @abstractmethod
    async def get_cache_hit_rate_for_task(self, task_id: str) -> float:
        """Cache-hit ratio for a single task across all of its CostRecords.

        Returns ratio in [0.0, 1.0] computed as
        ``sum(cached_tokens) / sum(prompt_tokens + cached_tokens)`` over all
        records whose ``task_id`` matches. Returns 0.0 when no records exist
        or when the denominator is zero (e.g. only engine costs were tracked).
        """

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

"""PlanRepository port — persistence abstraction for execution plans."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.plan import ExecutionPlan


class PlanRepository(ABC):
    @abstractmethod
    async def save(self, plan: ExecutionPlan) -> None: ...

    @abstractmethod
    async def get_by_id(self, plan_id: str) -> ExecutionPlan | None: ...

    @abstractmethod
    async def list_all(self) -> list[ExecutionPlan]: ...

    @abstractmethod
    async def update(self, plan: ExecutionPlan) -> None: ...

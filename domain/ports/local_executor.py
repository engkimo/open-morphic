"""LocalExecutorPort — abstraction for LAEE local execution."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.execution import Action, Observation


class LocalExecutorPort(ABC):
    @abstractmethod
    async def execute(self, action: Action) -> Observation: ...

    @abstractmethod
    async def undo_last(self) -> Observation: ...

    @abstractmethod
    async def get_undo_stack_size(self) -> int: ...

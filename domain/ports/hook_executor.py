"""Port for approved chat hook command execution."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.hook import HookExecutionRequest, HookExecutionResult


class HookExecutorPort(ABC):
    """Executes one normalized hook command through an infrastructure adapter."""

    @abstractmethod
    async def execute(self, request: HookExecutionRequest) -> HookExecutionResult: ...

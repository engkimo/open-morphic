"""LAEE-compatible implementation of the chat tool executor port."""

from __future__ import annotations

from domain.entities.execution import Action
from domain.ports.local_executor import LocalExecutorPort
from domain.ports.tool_executor import (
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolExecutorPort,
)
from domain.value_objects.status import ObservationStatus


class LaeeToolExecutor(ToolExecutorPort):
    def __init__(self, *, local_executor: LocalExecutorPort) -> None:
        self._local_executor = local_executor

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        observation = await self._local_executor.execute(
            Action(
                tool=request.tool_name,
                args=request.arguments,
                description=f"chat session {request.session_id}",
                risk=request.risk_level,
            )
        )
        success = observation.status is ObservationStatus.SUCCESS
        return ToolExecutionResult(
            request_id=request.id,
            success=success,
            stdout_summary=observation.result if success else "",
            stderr_summary="" if success else observation.result,
            exit_code=0 if success else 1,
        )

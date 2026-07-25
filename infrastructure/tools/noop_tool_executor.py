"""No-op implementation of the chat tool executor port."""

from __future__ import annotations

from domain.ports.tool_executor import (
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolExecutorPort,
)


class NoopToolExecutor(ToolExecutorPort):
    """Records tool execution intent without invoking local tools."""

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        return ToolExecutionResult(
            request_id=request.id,
            success=True,
            stdout_summary=f"Tool {request.tool_name} not executed by no-op executor.",
            stderr_summary="",
            exit_code=0,
        )

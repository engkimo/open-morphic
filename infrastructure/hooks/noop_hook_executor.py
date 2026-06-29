"""No-op implementation of the chat hook executor port."""

from __future__ import annotations

from domain.entities.hook import HookExecutionRequest, HookExecutionResult
from domain.ports.hook_executor import HookExecutorPort


class NoopHookExecutor(HookExecutorPort):
    """Records hook execution intent without invoking a shell command."""

    async def execute(self, request: HookExecutionRequest) -> HookExecutionResult:
        return HookExecutionResult(
            request_id=request.id,
            success=True,
            stdout_summary=f"Hook {request.hook_name} not executed by no-op executor.",
            stderr_summary="",
            exit_code=0,
        )

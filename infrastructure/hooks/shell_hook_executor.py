"""Shell-backed implementation of the chat hook executor port."""

from __future__ import annotations

from pathlib import Path

from domain.entities.execution import Action
from domain.entities.hook import HookExecutionRequest, HookExecutionResult
from domain.ports.hook_executor import HookExecutorPort
from domain.ports.local_executor import LocalExecutorPort
from domain.value_objects import RiskLevel
from domain.value_objects.status import ObservationStatus


class ShellHookExecutor(HookExecutorPort):
    """Execute hook commands through LAEE shell execution policy."""

    def __init__(
        self,
        *,
        local_executor: LocalExecutorPort,
        workspace_root: str | Path,
        timeout_seconds: int = 30,
    ) -> None:
        self._local_executor = local_executor
        self._workspace_root = Path(workspace_root)
        self._timeout_seconds = timeout_seconds

    async def execute(self, request: HookExecutionRequest) -> HookExecutionResult:
        observation = await self._local_executor.execute(
            Action(
                tool="shell_exec",
                args={
                    "cmd": request.command,
                    "cwd": str(self._workspace_root),
                    "timeout": self._timeout_seconds,
                },
                description=(
                    f"chat session {request.session_id} hook {request.hook_name} "
                    f"from {request.source_path}"
                ),
                risk=RiskLevel.MEDIUM,
            )
        )
        success = observation.status is ObservationStatus.SUCCESS
        return HookExecutionResult(
            request_id=request.id,
            success=success,
            stdout_summary=observation.result if success else "",
            stderr_summary="" if success else observation.result,
            exit_code=0 if success else 1,
        )

"""Tests for shell-backed chat hook execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.entities.execution import Action, Observation
from domain.entities.hook import HookExecutionRequest, HookType
from domain.ports.local_executor import LocalExecutorPort
from domain.value_objects.status import ObservationStatus
from infrastructure.hooks.shell_hook_executor import ShellHookExecutor


class FakeLocalExecutor(LocalExecutorPort):
    def __init__(self, *, status: ObservationStatus, result: str) -> None:
        self.actions: list[Action] = []
        self._status = status
        self._result = result

    async def execute(self, action: Action) -> Observation:
        self.actions.append(action)
        return Observation(status=self._status, result=self._result)

    async def undo_last(self) -> Observation:
        return Observation(status=ObservationStatus.SUCCESS, result="undone")

    async def get_undo_stack_size(self) -> int:
        return 0


def _request() -> HookExecutionRequest:
    return HookExecutionRequest(
        session_id="chat-1",
        hook_name="lint",
        hook_type=HookType.PRE_TOOL,
        command="uv run --extra dev ruff check .",
        source_path=".morphic/hooks/lint.json",
    )


@pytest.mark.asyncio
async def test_shell_hook_executor_maps_hook_to_laee_shell_exec(tmp_path: Path) -> None:
    local_executor = FakeLocalExecutor(
        status=ObservationStatus.SUCCESS,
        result="All checks passed",
    )

    result = await ShellHookExecutor(
        local_executor=local_executor,
        workspace_root=tmp_path,
        timeout_seconds=12,
    ).execute(_request())

    assert result.success
    assert result.stdout_summary == "All checks passed"
    assert result.exit_code == 0
    assert local_executor.actions[0].tool == "shell_exec"
    assert local_executor.actions[0].args == {
        "cmd": "uv run --extra dev ruff check .",
        "cwd": str(tmp_path),
        "timeout": 12,
    }
    assert "hook lint" in local_executor.actions[0].description


@pytest.mark.asyncio
async def test_shell_hook_executor_maps_denied_observation_to_failed_result(
    tmp_path: Path,
) -> None:
    local_executor = FakeLocalExecutor(
        status=ObservationStatus.DENIED,
        result="Action requires approval",
    )

    result = await ShellHookExecutor(
        local_executor=local_executor,
        workspace_root=tmp_path,
    ).execute(_request())

    assert result.success is False
    assert result.stdout_summary == ""
    assert result.stderr_summary == "Action requires approval"
    assert result.exit_code == 1

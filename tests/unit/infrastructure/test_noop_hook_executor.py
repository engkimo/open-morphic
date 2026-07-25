"""Tests for the no-op chat hook executor adapter."""

from __future__ import annotations

import pytest

from domain.entities.hook import HookExecutionRequest, HookType
from infrastructure.hooks.noop_hook_executor import NoopHookExecutor


@pytest.mark.asyncio
async def test_noop_hook_executor_returns_success_without_running_command() -> None:
    executor = NoopHookExecutor()
    request = HookExecutionRequest(
        session_id="chat-1",
        hook_name="pre-log",
        hook_type=HookType.PRE_TOOL,
        command="exit 99",
        source_path=".morphic/hooks/pre-log.json",
    )

    result = await executor.execute(request)

    assert result.request_id == request.id
    assert result.success
    assert result.exit_code == 0
    assert "not executed" in result.stdout_summary

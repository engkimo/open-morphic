"""Tests for the no-op chat tool executor adapter."""

from __future__ import annotations

import pytest

from domain.ports.tool_executor import ToolExecutionRequest
from infrastructure.tools.noop_tool_executor import NoopToolExecutor


@pytest.mark.asyncio
async def test_noop_tool_executor_returns_success_without_running_tool() -> None:
    executor = NoopToolExecutor()
    request = ToolExecutionRequest(
        session_id="chat-1",
        tool_name="fs_write",
        arguments={"path": "x.txt", "content": "x"},
    )

    result = await executor.execute(request)

    assert result.request_id == request.id
    assert result.success
    assert result.exit_code == 0
    assert "not executed" in result.stdout_summary

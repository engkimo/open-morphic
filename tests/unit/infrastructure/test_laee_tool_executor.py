"""Tests for LAEE-compatible chat tool executor adapter."""

from __future__ import annotations

import pytest

from domain.entities.execution import Action, Observation
from domain.ports.local_executor import LocalExecutorPort
from domain.ports.tool_executor import ToolExecutionRequest
from domain.value_objects import RiskLevel
from domain.value_objects.status import ObservationStatus
from infrastructure.tools.laee_tool_executor import LaeeToolExecutor


class FakeLocalExecutor(LocalExecutorPort):
    def __init__(self) -> None:
        self.actions: list[Action] = []

    async def execute(self, action: Action) -> Observation:
        self.actions.append(action)
        return Observation(status=ObservationStatus.SUCCESS, result="created file")

    async def undo_last(self) -> Observation:
        return Observation(status=ObservationStatus.SUCCESS, result="undone")

    async def get_undo_stack_size(self) -> int:
        return 0


@pytest.mark.asyncio
async def test_laee_tool_executor_maps_request_to_action_and_result() -> None:
    local_executor = FakeLocalExecutor()
    executor = LaeeToolExecutor(local_executor=local_executor)
    request = ToolExecutionRequest(
        session_id="chat-1",
        tool_name="fs_write",
        arguments={"path": "x.txt", "content": "x"},
        risk_level=RiskLevel.MEDIUM,
    )

    result = await executor.execute(request)

    assert result.success
    assert result.request_id == request.id
    assert result.stdout_summary == "created file"
    assert local_executor.actions[0].tool == "fs_write"
    assert local_executor.actions[0].risk is RiskLevel.MEDIUM

"""Application tests for Morphic Chat CLI Phase 5 tool execution."""

from __future__ import annotations

import pytest

from application.use_cases.execute_chat_tool import ExecuteChatToolUseCase
from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.entities.chat_session import ChatSession, PermissionMode
from domain.ports.chat_session_store import ChatSessionStorePort
from domain.ports.tool_executor import (
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolExecutorPort,
)
from domain.value_objects import RiskLevel


class InMemoryChatSessionStore(ChatSessionStorePort):
    def __init__(self) -> None:
        self.appended: list[ChatEvent] = []

    async def append_event(self, event: ChatEvent) -> None:
        self.appended.append(event)

    async def load_events(self, session_id: str) -> list[ChatEvent]:
        return [event for event in self.appended if event.session_id == session_id]

    async def latest_session_id(self) -> str | None:
        return self.appended[-1].session_id if self.appended else None


class FakeToolExecutor(ToolExecutorPort):
    def __init__(self) -> None:
        self.requests: list[ToolExecutionRequest] = []

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        self.requests.append(request)
        return ToolExecutionResult(
            request_id=request.id,
            success=True,
            stdout_summary="ok",
            stderr_summary="",
            exit_code=0,
            artifacts=["result.txt"],
        )


@pytest.mark.asyncio
async def test_read_only_session_blocks_mutating_tool() -> None:
    store = InMemoryChatSessionStore()
    executor = FakeToolExecutor()
    session = ChatSession.start(
        session_id="chat-1",
        goal="inspect only",
        permission_mode=PermissionMode.READ_ONLY,
    )

    with pytest.raises(PermissionError):
        await ExecuteChatToolUseCase(
            session_store=store,
            tool_executor=executor,
        ).execute(
            session=session,
            tool_name="fs_write",
            arguments={"path": "x.txt", "content": "x"},
            risk_level=RiskLevel.MEDIUM,
        )

    assert executor.requests == []
    assert store.appended == []


@pytest.mark.asyncio
async def test_execute_tool_records_diff_tool_and_verification_events() -> None:
    store = InMemoryChatSessionStore()
    executor = FakeToolExecutor()
    session = ChatSession.start(
        session_id="chat-1",
        goal="write file",
        permission_mode=PermissionMode.WORKSPACE_WRITE,
    )

    result = await ExecuteChatToolUseCase(
        session_store=store,
        tool_executor=executor,
    ).execute(
        session=session,
        tool_name="fs_write",
        arguments={"path": "x.txt", "content": "x"},
        risk_level=RiskLevel.MEDIUM,
        diff_summary="create x.txt",
        verification_label="unit tests",
    )

    assert result.tool_result.success
    assert [event.type for event in result.events] == [
        ChatEventType.DIFF_PROPOSED,
        ChatEventType.TOOL_CALL_REQUESTED,
        ChatEventType.TOOL_CALL_COMPLETED,
        ChatEventType.VERIFICATION_RESULT,
    ]
    assert result.events[0].payload["summary"] == "create x.txt"
    assert result.events[-1].payload["label"] == "unit tests"
    assert result.session.next_sequence == 4

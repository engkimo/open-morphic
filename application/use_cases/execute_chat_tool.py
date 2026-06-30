"""ExecuteChatToolUseCase — record and execute chat tool requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.use_cases.execute_chat_hook import ExecuteChatHookUseCase
from application.use_cases.plan_chat_hooks import PlanChatHooksUseCase
from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.entities.chat_session import ChatSession, PermissionMode
from domain.entities.hook import HookExecutionResult, HookType
from domain.ports.chat_session_store import ChatSessionStorePort
from domain.ports.tool_executor import (
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolExecutorPort,
)
from domain.value_objects import RiskLevel

_READ_ONLY_TOOLS = {"fs_read", "fs_list", "grep", "search", "git_status", "git_diff"}


@dataclass(frozen=True)
class ExecuteChatToolResult:
    session: ChatSession
    request: ToolExecutionRequest
    tool_result: ToolExecutionResult
    events: list[ChatEvent]


class ExecuteChatToolUseCase:
    def __init__(
        self,
        *,
        session_store: ChatSessionStorePort,
        tool_executor: ToolExecutorPort,
        hook_planner: PlanChatHooksUseCase | None = None,
        hook_runner: ExecuteChatHookUseCase | None = None,
    ) -> None:
        self._session_store = session_store
        self._tool_executor = tool_executor
        self._hook_planner = hook_planner
        self._hook_runner = hook_runner

    async def execute(
        self,
        *,
        session: ChatSession,
        tool_name: str,
        arguments: dict[str, Any],
        risk_level: RiskLevel,
        requires_approval: bool = False,
        approval_id: str | None = None,
        diff_summary: str | None = None,
        verification_label: str | None = None,
    ) -> ExecuteChatToolResult:
        if self._blocked_by_read_only(session, tool_name, risk_level):
            raise PermissionError(f"read-only session cannot execute mutating tool: {tool_name}")

        current = session
        events: list[ChatEvent] = []
        if self._hook_runner is not None:
            hook_result = await self._hook_runner.execute(
                session=current,
                hook_type=HookType.PRE_TOOL,
            )
            current = hook_result.session
            events.extend(hook_result.events)
            self._raise_if_hook_failed(hook_result.hook_results, HookType.PRE_TOOL)
        elif self._hook_planner is not None:
            hook_result = await self._hook_planner.execute(
                session=current,
                hook_type=HookType.PRE_TOOL,
            )
            current = hook_result.session
            events.extend(hook_result.events)

        tool_events: list[ChatEvent] = []
        if diff_summary:
            current, diff_event = current.record_event(
                ChatEventType.DIFF_PROPOSED,
                {"summary": diff_summary, "tool_name": tool_name},
            )
            tool_events.append(diff_event)

        request = ToolExecutionRequest(
            session_id=session.id,
            tool_name=tool_name,
            arguments=arguments,
            risk_level=risk_level,
            requires_approval=requires_approval,
            approval_id=approval_id,
        )
        current, requested_event = current.record_event(
            ChatEventType.TOOL_CALL_REQUESTED,
            request.model_dump(mode="json"),
        )
        tool_events.append(requested_event)

        tool_result = await self._tool_executor.execute(request)
        current, completed_event = current.record_event(
            ChatEventType.TOOL_CALL_COMPLETED,
            tool_result.model_dump(mode="json"),
        )
        tool_events.append(completed_event)

        if verification_label:
            current, verification_event = current.record_event(
                ChatEventType.VERIFICATION_RESULT,
                {
                    "label": verification_label,
                    "success": tool_result.success,
                    "request_id": request.id,
                },
            )
            tool_events.append(verification_event)

        if self._hook_runner is not None:
            for event in tool_events:
                await self._session_store.append_event(event)
            events.extend(tool_events)
            hook_result = await self._hook_runner.execute(
                session=current,
                hook_type=HookType.POST_TOOL,
            )
            current = hook_result.session
            events.extend(hook_result.events)
        elif self._hook_planner is not None:
            for event in tool_events:
                await self._session_store.append_event(event)
            events.extend(tool_events)
            hook_result = await self._hook_planner.execute(
                session=current,
                hook_type=HookType.POST_TOOL,
            )
            current = hook_result.session
            events.extend(hook_result.events)
        else:
            events.extend(tool_events)
            for event in events:
                await self._session_store.append_event(event)

        return ExecuteChatToolResult(
            session=current,
            request=request,
            tool_result=tool_result,
            events=events,
        )

    def _blocked_by_read_only(
        self,
        session: ChatSession,
        tool_name: str,
        risk_level: RiskLevel,
    ) -> bool:
        if session.permission_mode is not PermissionMode.READ_ONLY:
            return False
        return risk_level > RiskLevel.SAFE or tool_name not in _READ_ONLY_TOOLS

    def _raise_if_hook_failed(
        self,
        hook_results: list[HookExecutionResult],
        hook_type: HookType,
    ) -> None:
        failed = [result for result in hook_results if not result.success]
        if failed:
            raise RuntimeError(f"{hook_type.value} hook failed")

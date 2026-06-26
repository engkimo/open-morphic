"""Application tests for Morphic Chat CLI hook execution planning."""

from __future__ import annotations

import pytest

from application.use_cases.plan_chat_hooks import PlanChatHooksUseCase
from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.entities.chat_session import ChatSession, PermissionMode
from domain.entities.hook import HookDefinition, HookDiagnostic, HookType
from domain.ports.chat_session_store import ChatSessionStorePort
from domain.ports.hook_registry import HookRegistryPort

pytestmark = pytest.mark.asyncio


class InMemoryChatSessionStore(ChatSessionStorePort):
    def __init__(self) -> None:
        self.appended: list[ChatEvent] = []

    async def append_event(self, event: ChatEvent) -> None:
        self.appended.append(event)

    async def load_events(self, session_id: str) -> list[ChatEvent]:
        return [event for event in self.appended if event.session_id == session_id]

    async def latest_session_id(self) -> str | None:
        return self.appended[-1].session_id if self.appended else None


class FakeHookRegistry(HookRegistryPort):
    def __init__(
        self,
        *,
        diagnostics: list[HookDiagnostic],
        hooks: list[HookDefinition],
    ) -> None:
        self._diagnostics = diagnostics
        self._hooks = hooks

    def validate(self) -> list[HookDiagnostic]:
        return self._diagnostics

    def hooks_for(self, hook_type: HookType) -> list[HookDefinition]:
        return [hook for hook in self._hooks if hook.hook_type is hook_type]


def _session() -> ChatSession:
    return ChatSession.start(
        session_id="chat-1",
        goal="run hooks",
        permission_mode=PermissionMode.CONFIRM_DESTRUCTIVE,
    )


async def test_plan_chat_hooks_records_enabled_hook_plan_event() -> None:
    store = InMemoryChatSessionStore()
    registry = FakeHookRegistry(
        diagnostics=[
            HookDiagnostic(
                name="Hook: lint",
                status="OK",
                message="pre_commit hook is valid",
            )
        ],
        hooks=[
            HookDefinition(
                name="lint",
                hook_type=HookType.PRE_COMMIT,
                command="uv run --extra dev ruff check .",
                enabled=True,
                source_path=".morphic/hooks/lint.json",
            )
        ],
    )

    result = await PlanChatHooksUseCase(
        session_store=store,
        hook_registry=registry,
    ).execute(session=_session(), hook_type=HookType.PRE_COMMIT)

    assert [event.type for event in result.events] == [
        ChatEventType.HOOK_EXECUTION_PLANNED
    ]
    assert result.events[0].payload == {
        "command": "uv run --extra dev ruff check .",
        "hook_name": "lint",
        "hook_type": "pre_commit",
        "source_path": ".morphic/hooks/lint.json",
        "status": "planned",
    }
    assert store.appended == result.events
    assert result.session.next_sequence == 1


async def test_plan_chat_hooks_records_disabled_hook_skip_event() -> None:
    store = InMemoryChatSessionStore()
    registry = FakeHookRegistry(
        diagnostics=[
            HookDiagnostic(
                name="Hook: disabled",
                status="WARN",
                message="pre_shell hook is disabled",
            )
        ],
        hooks=[
            HookDefinition(
                name="disabled",
                hook_type=HookType.PRE_SHELL,
                command="echo skipped",
                enabled=False,
                source_path=".morphic/hooks/disabled.json",
            )
        ],
    )

    result = await PlanChatHooksUseCase(
        session_store=store,
        hook_registry=registry,
    ).execute(session=_session(), hook_type=HookType.PRE_SHELL)

    assert [event.type for event in result.events] == [
        ChatEventType.HOOK_EXECUTION_SKIPPED
    ]
    assert result.events[0].payload["reason"] == "disabled"
    assert result.events[0].payload["status"] == "skipped"


async def test_plan_chat_hooks_blocks_when_hook_diagnostics_fail() -> None:
    store = InMemoryChatSessionStore()
    registry = FakeHookRegistry(
        diagnostics=[
            HookDiagnostic(
                name="Hook: secret",
                status="FAIL",
                message="command references a secret path",
            )
        ],
        hooks=[],
    )

    with pytest.raises(ValueError) as exc_info:
        await PlanChatHooksUseCase(
            session_store=store,
            hook_registry=registry,
        ).execute(session=_session(), hook_type=HookType.PRE_SHELL)

    assert "Hook diagnostics failed" in str(exc_info.value)
    assert store.appended == []

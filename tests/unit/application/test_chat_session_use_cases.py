"""Application use case tests for Morphic Chat CLI Phase 2."""

from __future__ import annotations

import pytest

from application.use_cases.discover_workspace_context import (
    DiscoverWorkspaceContextUseCase,
)
from application.use_cases.execute_slash_command import ExecuteSlashCommandUseCase
from application.use_cases.request_tool_approval import RequestToolApprovalUseCase
from application.use_cases.resume_chat_session import ResumeChatSessionUseCase
from application.use_cases.send_chat_message import SendChatMessageUseCase
from application.use_cases.start_chat_session import StartChatSessionUseCase
from application.use_cases.summarize_chat_session import SummarizeChatSessionUseCase
from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.entities.chat_session import ChatSessionStatus, PermissionMode
from domain.entities.council_runtime import CouncilDecision, CouncilRole, CouncilTurn
from domain.entities.workspace_context import (
    ContextIndex,
    ContextSourceType,
    WorkspaceContextSource,
)
from domain.ports.chat_session_store import ChatSessionStorePort
from domain.ports.context_discovery import ContextDiscoveryPort
from domain.ports.council_runtime import CouncilRuntimePort
from domain.ports.engine_registry import EngineProfile, EngineRegistryPort, EngineRuntimeKind
from domain.value_objects import RiskLevel


class InMemoryChatSessionStore(ChatSessionStorePort):
    def __init__(self) -> None:
        self.events_by_session: dict[str, list[ChatEvent]] = {}
        self.appended: list[ChatEvent] = []

    async def append_event(self, event: ChatEvent) -> None:
        self.events_by_session.setdefault(event.session_id, []).append(event)
        self.appended.append(event)

    async def load_events(self, session_id: str) -> list[ChatEvent]:
        return list(self.events_by_session.get(session_id, []))

    async def latest_session_id(self) -> str | None:
        if not self.appended:
            return None
        return self.appended[-1].session_id


class FakeContextDiscovery(ContextDiscoveryPort):
    async def discover(self, workspace_root: str) -> ContextIndex:
        return ContextIndex(
            workspace_root=workspace_root,
            sources=[
                WorkspaceContextSource(
                    source_path="AGENTS.md",
                    source_type=ContextSourceType.AGENTS_MD,
                    scope="root",
                    precedence=100,
                    content_hash="sha256:test",
                    sections=["Start"],
                )
            ],
        )


class FakeCouncilRuntime(CouncilRuntimePort):
    async def deliberate(
        self,
        session,
        context: ContextIndex,
        user_message: str,
    ) -> tuple[list[CouncilTurn], CouncilDecision]:
        return (
            [
                CouncilTurn(
                    role=CouncilRole.PLANNER,
                    engine_id="ollama",
                    content=f"Plan for {user_message}",
                    evidence=[context.workspace_root],
                )
            ],
            CouncilDecision(
                leader_engine_id="direct_llm",
                selected_role=CouncilRole.PLANNER,
                selected_content="Start with application use cases.",
                rationale="Matches Phase 2 tasks.",
                evidence=["tasks.md"],
            ),
        )


class FakeEngineRegistry(EngineRegistryPort):
    async def list_engines(self) -> list[EngineProfile]:
        return [
            EngineProfile(
                id="ollama",
                display_name="Ollama",
                kind=EngineRuntimeKind.LOCAL_MODEL,
                available=True,
                capabilities=["planning"],
            )
        ]

    async def get_engine(self, engine_id: str) -> EngineProfile | None:
        engines = await self.list_engines()
        return next((engine for engine in engines if engine.id == engine_id), None)


@pytest.mark.asyncio
async def test_start_chat_session_appends_session_started_event() -> None:
    store = InMemoryChatSessionStore()
    use_case = StartChatSessionUseCase(session_store=store)

    result = await use_case.execute(
        goal="Build chat CLI",
        permission_mode=PermissionMode.CONFIRM_DESTRUCTIVE,
        session_id="chat-1",
    )

    assert result.session.id == "chat-1"
    assert result.session.next_sequence == 1
    assert result.event.type is ChatEventType.SESSION_STARTED
    assert result.event.sequence == 0
    assert store.appended == [result.event]


@pytest.mark.asyncio
async def test_resume_latest_rebuilds_session_sequence_from_events() -> None:
    store = InMemoryChatSessionStore()
    started = await StartChatSessionUseCase(session_store=store).execute(
        goal="Build chat CLI",
        permission_mode=PermissionMode.READ_ONLY,
        session_id="chat-1",
    )
    await store.append_event(
        ChatEvent(
            type=ChatEventType.USER_MESSAGE,
            session_id="chat-1",
            sequence=1,
            payload={"text": "continue"},
        )
    )

    result = await ResumeChatSessionUseCase(session_store=store).execute("latest")

    assert result.session.id == "chat-1"
    assert result.session.next_sequence == 2
    assert result.session.permission_mode is PermissionMode.READ_ONLY
    assert result.events[0] == started.event


@pytest.mark.asyncio
async def test_send_chat_message_appends_user_council_and_assistant_events() -> None:
    store = InMemoryChatSessionStore()
    session = (
        await StartChatSessionUseCase(session_store=store).execute(
            goal="Build chat CLI",
            permission_mode=PermissionMode.CONFIRM_DESTRUCTIVE,
            session_id="chat-1",
        )
    ).session
    context = await FakeContextDiscovery().discover("/repo")
    use_case = SendChatMessageUseCase(
        session_store=store,
        council_runtime=FakeCouncilRuntime(),
    )

    result = await use_case.execute(
        session=session,
        context=context,
        message="implement Phase 2",
    )

    assert result.session.next_sequence == 5
    assert [event.type for event in result.events] == [
        ChatEventType.USER_MESSAGE,
        ChatEventType.COUNCIL_ARGUMENT,
        ChatEventType.COUNCIL_DECISION,
        ChatEventType.ASSISTANT_MESSAGE,
    ]
    assert result.events[-1].payload["text"] == "Start with application use cases."


@pytest.mark.asyncio
async def test_discover_workspace_context_appends_context_indexed_event() -> None:
    store = InMemoryChatSessionStore()
    session = (
        await StartChatSessionUseCase(session_store=store).execute(
            goal=None,
            permission_mode=PermissionMode.READ_ONLY,
            session_id="chat-1",
        )
    ).session
    use_case = DiscoverWorkspaceContextUseCase(
        context_discovery=FakeContextDiscovery(),
        session_store=store,
    )

    result = await use_case.execute(workspace_root="/repo", session=session)

    assert result.index.workspace_root == "/repo"
    assert result.session is not None
    assert result.session.next_sequence == 2
    assert result.event is not None
    assert result.event.type is ChatEventType.CONTEXT_INDEXED
    assert result.event.payload["source_count"] == 1


@pytest.mark.asyncio
async def test_request_tool_approval_marks_session_waiting_and_appends_event() -> None:
    store = InMemoryChatSessionStore()
    session = (
        await StartChatSessionUseCase(session_store=store).execute(
            goal="Build chat CLI",
            permission_mode=PermissionMode.CONFIRM_DESTRUCTIVE,
            session_id="chat-1",
        )
    ).session

    result = await RequestToolApprovalUseCase(session_store=store).execute(
        session=session,
        action_summary="Edit files",
        risk_level=RiskLevel.MEDIUM,
        reason="workspace mutation",
    )

    assert result.session.status is ChatSessionStatus.WAITING_FOR_APPROVAL
    assert result.request.risk_level is RiskLevel.MEDIUM
    assert result.event.type is ChatEventType.APPROVAL_REQUESTED


@pytest.mark.asyncio
async def test_execute_slash_command_status_engines_and_quit() -> None:
    store = InMemoryChatSessionStore()
    session = (
        await StartChatSessionUseCase(session_store=store).execute(
            goal="Build chat CLI",
            permission_mode=PermissionMode.READ_ONLY,
            session_id="chat-1",
        )
    ).session
    context = await FakeContextDiscovery().discover("/repo")
    use_case = ExecuteSlashCommandUseCase(
        session_store=store,
        engine_registry=FakeEngineRegistry(),
    )

    status = await use_case.execute(session=session, command="/status", context=context)
    engines = await use_case.execute(
        session=status.session,
        command="/engines",
        context=context,
    )
    quit_result = await use_case.execute(
        session=engines.session,
        command="/quit",
        context=context,
    )

    assert "chat-1" in status.output
    assert "ollama" in engines.output
    assert quit_result.should_exit
    assert quit_result.session.status is ChatSessionStatus.ENDED


@pytest.mark.asyncio
async def test_summarize_chat_session_appends_summary_event() -> None:
    store = InMemoryChatSessionStore()
    await StartChatSessionUseCase(session_store=store).execute(
        goal="Build chat CLI",
        permission_mode=PermissionMode.READ_ONLY,
        session_id="chat-1",
    )
    await store.append_event(
        ChatEvent(
            type=ChatEventType.USER_MESSAGE,
            session_id="chat-1",
            sequence=1,
            payload={"text": "hello"},
        )
    )

    result = await SummarizeChatSessionUseCase(session_store=store).execute("chat-1")

    assert result.event.type is ChatEventType.SESSION_SUMMARY
    assert result.event.sequence == 2
    assert result.summary["event_counts"]["user_message"] == 1

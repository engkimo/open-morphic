"""ResumeChatSessionUseCase — rebuild chat session state from stored events."""

from __future__ import annotations

from dataclasses import dataclass

from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.entities.chat_session import ChatSession, ChatSessionStatus, PermissionMode
from domain.ports.chat_session_store import ChatSessionStorePort


@dataclass(frozen=True)
class ResumeChatSessionResult:
    session: ChatSession
    events: list[ChatEvent]


class ResumeChatSessionUseCase:
    def __init__(self, *, session_store: ChatSessionStorePort) -> None:
        self._session_store = session_store

    async def execute(self, session_id: str) -> ResumeChatSessionResult:
        resolved_session_id = session_id
        if session_id == "latest":
            latest = await self._session_store.latest_session_id()
            if latest is None:
                raise ValueError("no chat sessions available to resume")
            resolved_session_id = latest

        events = await self._session_store.load_events(resolved_session_id)
        if not events:
            raise ValueError(f"chat session not found: {resolved_session_id}")

        started = events[0]
        goal = None
        permission_mode = PermissionMode.CONFIRM_DESTRUCTIVE
        if started.type is ChatEventType.SESSION_STARTED:
            goal = started.payload.get("goal")
            mode_value = started.payload.get("permission_mode")
            if isinstance(mode_value, str):
                permission_mode = PermissionMode(mode_value)

        status = ChatSessionStatus.ACTIVE
        if any(event.type is ChatEventType.SESSION_ENDED for event in events):
            status = ChatSessionStatus.ENDED

        session = ChatSession(
            id=resolved_session_id,
            goal=goal,
            permission_mode=permission_mode,
            status=status,
            next_sequence=max(event.sequence for event in events) + 1,
        )
        return ResumeChatSessionResult(session=session, events=events)

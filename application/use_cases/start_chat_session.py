"""StartChatSessionUseCase — create a chat session and append start event."""

from __future__ import annotations

from dataclasses import dataclass

from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.entities.chat_session import ChatSession, PermissionMode
from domain.ports.chat_session_store import ChatSessionStorePort


@dataclass(frozen=True)
class StartChatSessionResult:
    session: ChatSession
    event: ChatEvent


class StartChatSessionUseCase:
    def __init__(self, *, session_store: ChatSessionStorePort) -> None:
        self._session_store = session_store

    async def execute(
        self,
        *,
        goal: str | None,
        permission_mode: PermissionMode,
        session_id: str | None = None,
    ) -> StartChatSessionResult:
        session = ChatSession.start(
            session_id=session_id,
            goal=goal,
            permission_mode=permission_mode,
        )
        updated, event = session.record_event(
            ChatEventType.SESSION_STARTED,
            {
                "goal": goal,
                "permission_mode": permission_mode.value,
            },
        )
        await self._session_store.append_event(event)
        return StartChatSessionResult(session=updated, event=event)

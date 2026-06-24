"""SummarizeChatSessionUseCase — create a lightweight session summary event."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.ports.chat_session_store import ChatSessionStorePort


@dataclass(frozen=True)
class SummarizeChatSessionResult:
    summary: dict[str, Any]
    event: ChatEvent


class SummarizeChatSessionUseCase:
    def __init__(self, *, session_store: ChatSessionStorePort) -> None:
        self._session_store = session_store

    async def execute(self, session_id: str) -> SummarizeChatSessionResult:
        events = await self._session_store.load_events(session_id)
        if not events:
            raise ValueError(f"chat session not found: {session_id}")

        counts = Counter(event.type.value for event in events)
        last_sequence = max(event.sequence for event in events)
        summary = {
            "session_id": session_id,
            "event_count": len(events),
            "event_counts": dict(sorted(counts.items())),
        }
        event = ChatEvent(
            type=ChatEventType.SESSION_SUMMARY,
            session_id=session_id,
            sequence=last_sequence + 1,
            payload=summary,
        )
        await self._session_store.append_event(event)
        return SummarizeChatSessionResult(summary=summary, event=event)

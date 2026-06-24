"""Port for append-only chat session persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.chat_event import ChatEvent


class ChatSessionStorePort(ABC):
    """Append-only storage contract for chat session events."""

    @abstractmethod
    async def append_event(self, event: ChatEvent) -> None: ...

    @abstractmethod
    async def load_events(self, session_id: str) -> list[ChatEvent]: ...

    @abstractmethod
    async def latest_session_id(self) -> str | None: ...

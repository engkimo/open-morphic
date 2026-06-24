"""Render helpers for Morphic Chat CLI."""

from __future__ import annotations

from domain.entities.chat_event import ChatEvent, ChatEventType


def render_chat_event(event: ChatEvent) -> str | None:
    if event.type is ChatEventType.ASSISTANT_MESSAGE:
        text = event.payload.get("text")
        return str(text) if text else None
    if event.type is ChatEventType.SESSION_ENDED:
        return "session ended"
    return None

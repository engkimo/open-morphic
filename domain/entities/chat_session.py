"""Chat session entity for Morphic Chat CLI."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.entities.chat_event import ChatEvent, ChatEventType


class PermissionMode(str, Enum):
    """Workspace permission mode for chat execution."""

    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    CONFIRM_DESTRUCTIVE = "confirm-destructive"
    DANGER_FULL_ACCESS = "danger-full-access"


class ChatSessionStatus(str, Enum):
    """Lifecycle state for a chat session."""

    ACTIVE = "active"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    PAUSED = "paused"
    ENDED = "ended"


class ChatSession(BaseModel):
    """Session state used to sequence append-only chat events."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1)
    status: ChatSessionStatus = ChatSessionStatus.ACTIVE
    goal: str | None = Field(default=None, min_length=1)
    permission_mode: PermissionMode = PermissionMode.CONFIRM_DESTRUCTIVE
    next_sequence: int = Field(default=0, ge=0)

    @classmethod
    def start(
        cls,
        *,
        session_id: str | None = None,
        goal: str | None = None,
        permission_mode: PermissionMode = PermissionMode.CONFIRM_DESTRUCTIVE,
    ) -> ChatSession:
        return cls(
            id=session_id or str(uuid.uuid4()),
            goal=goal,
            permission_mode=permission_mode,
        )

    def record_event(
        self,
        event_type: ChatEventType,
        payload: dict[str, Any],
        *,
        created_at: datetime | None = None,
    ) -> tuple[ChatSession, ChatEvent]:
        event = ChatEvent(
            type=event_type,
            session_id=self.id,
            sequence=self.next_sequence,
            created_at=created_at or datetime.now(tz=UTC),
            payload=payload,
        )
        updated = self.model_copy(update={"next_sequence": self.next_sequence + 1})
        return updated, event

    def close(self) -> ChatSession:
        return self.model_copy(update={"status": ChatSessionStatus.ENDED})

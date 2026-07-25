"""Chat session entity for Morphic Chat CLI."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.value_objects.agent_engine import AgentEngineType


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


class NativeEngineSession(BaseModel):
    """Native thread identity bound to its original safety scope."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    engine: AgentEngineType
    session_id: str = Field(min_length=1)
    workspace_root: str = Field(min_length=1)
    permission_mode: PermissionMode


class ChatSession(BaseModel):
    """Session state used to sequence append-only chat events."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1)
    status: ChatSessionStatus = ChatSessionStatus.ACTIVE
    goal: str | None = Field(default=None, min_length=1)
    permission_mode: PermissionMode = PermissionMode.CONFIRM_DESTRUCTIVE
    workspace_root: str | None = Field(default=None, min_length=1)
    native_sessions: dict[str, NativeEngineSession] = Field(default_factory=dict)
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
        updated = self._apply_event_state(
            event_type=event_type,
            payload=payload,
            next_sequence=self.next_sequence + 1,
        )
        return updated, event

    def replay_event(self, event: ChatEvent) -> ChatSession:
        """Apply one already-persisted event without creating a replacement."""
        if event.session_id != self.id:
            raise ValueError("cannot replay event from another chat session")
        return self._apply_event_state(
            event_type=event.type,
            payload=event.payload,
            next_sequence=max(self.next_sequence, event.sequence + 1),
        )

    def _apply_event_state(
        self,
        *,
        event_type: ChatEventType,
        payload: dict[str, Any],
        next_sequence: int,
    ) -> ChatSession:
        updates: dict[str, Any] = {"next_sequence": next_sequence}
        if event_type is ChatEventType.CONTEXT_INDEXED:
            workspace_root = payload.get("workspace_root")
            if isinstance(workspace_root, str) and workspace_root:
                updates["workspace_root"] = workspace_root
        elif event_type is ChatEventType.ENGINE_EVENT:
            engine_value = payload.get("engine")
            session_id = payload.get("session_id")
            if (
                isinstance(engine_value, str)
                and isinstance(session_id, str)
                and session_id
                and self.workspace_root
            ):
                try:
                    engine = AgentEngineType(engine_value)
                except ValueError:
                    pass
                else:
                    native_sessions = dict(self.native_sessions)
                    native_sessions[engine.value] = NativeEngineSession(
                        engine=engine,
                        session_id=session_id,
                        workspace_root=self.workspace_root,
                        permission_mode=self.permission_mode,
                    )
                    updates["native_sessions"] = native_sessions
        elif event_type is ChatEventType.SESSION_ENDED:
            updates["status"] = ChatSessionStatus.ENDED
        return self.model_copy(update=updates)

    def close(self) -> ChatSession:
        return self.model_copy(update={"status": ChatSessionStatus.ENDED})

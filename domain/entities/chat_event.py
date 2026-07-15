"""Chat session events for the Morphic Chat CLI ledger."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChatEventType(str, Enum):
    """Append-only event vocabulary for chat sessions."""

    SESSION_STARTED = "session_started"
    CONTEXT_INDEXED = "context_indexed"
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    SLASH_COMMAND = "slash_command"
    COUNCIL_STARTED = "council_started"
    COUNCIL_ARGUMENT = "council_argument"
    COUNCIL_DECISION = "council_decision"
    ENGINE_EVENT = "engine_event"
    TOOL_CALL_REQUESTED = "tool_call_requested"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESOLVED = "approval_resolved"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    DIFF_PROPOSED = "diff_proposed"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_RESULT = "verification_result"
    HOOK_EXECUTION_PLANNED = "hook_execution_planned"
    HOOK_EXECUTION_SKIPPED = "hook_execution_skipped"
    HOOK_EXECUTION_REQUESTED = "hook_execution_requested"
    HOOK_EXECUTION_COMPLETED = "hook_execution_completed"
    MEMORY_CANDIDATE = "memory_candidate"
    SESSION_SUMMARY = "session_summary"
    SESSION_ENDED = "session_ended"


class ChatEvent(BaseModel):
    """One replayable event in a chat session ledger."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1)
    type: ChatEventType
    session_id: str = Field(min_length=1)
    sequence: int = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    payload: dict[str, Any] = Field(default_factory=dict)

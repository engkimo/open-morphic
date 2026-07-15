"""Normalized event vocabulary for native agent engine runs."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects.agent_engine import AgentEngineType


class AgentEngineEventType(str, Enum):
    """Provider-independent lifecycle events emitted by native agent engines."""

    RUN_STARTED = "run_started"
    TURN_STARTED = "turn_started"
    PROGRESS = "progress"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    FILE_CHANGED = "file_changed"
    PLAN_UPDATED = "plan_updated"
    ASSISTANT_MESSAGE = "assistant_message"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    ERROR = "error"
    UNKNOWN = "unknown"


class AgentEngineEvent(BaseModel):
    """One normalized native-engine event with the raw provider payload retained."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    type: AgentEngineEventType
    engine: AgentEngineType
    sequence: int = Field(ge=0)
    session_id: str | None = None
    item_id: str | None = None
    item_type: str | None = None
    text: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

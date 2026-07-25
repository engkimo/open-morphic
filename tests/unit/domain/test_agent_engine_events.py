"""Domain tests for normalized native agent engine events."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.entities.agent_engine_event import AgentEngineEvent, AgentEngineEventType
from domain.value_objects.agent_engine import AgentEngineType


def test_agent_engine_event_is_strict_immutable_and_serializable() -> None:
    event = AgentEngineEvent(
        type=AgentEngineEventType.TOOL_STARTED,
        engine=AgentEngineType.CODEX_CLI,
        sequence=2,
        session_id="thread-1",
        item_id="item-1",
        item_type="command_execution",
        text="pytest -q",
        payload={"status": "in_progress"},
    )

    assert event.model_dump(mode="json")["type"] == "tool_started"
    with pytest.raises(ValidationError):
        event.sequence = 3


def test_agent_engine_event_rejects_negative_sequence() -> None:
    with pytest.raises(ValidationError):
        AgentEngineEvent(
            type=AgentEngineEventType.RUN_STARTED,
            engine=AgentEngineType.CODEX_CLI,
            sequence=-1,
        )

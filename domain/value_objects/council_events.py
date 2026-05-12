"""Council debate events — immutable, publish-only event vocabulary.

These events are value objects (no identity beyond their data) emitted by the
council debate use case and consumed by `EventBusPort` implementations. The
`DebateEvent` discriminated union is the contract that the next sprint's
SSE/WebSocket renderer subscribes to.

Spec: `specs/council-pilot/spec.md` (FR-3, FR-4).
Plan: `specs/council-pilot/plan.md` §Data Model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from domain.entities.cognitive import Decision
from domain.entities.council import Argument, SubtaskBrief
from domain.value_objects.agent_engine import AgentEngineType


class _BaseEvent(BaseModel):
    debate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class DebateStarted(_BaseEvent):
    kind: Literal["debate_started"] = "debate_started"
    subtask: SubtaskBrief
    candidates: list[AgentEngineType]
    started_at: datetime = Field(default_factory=datetime.now)


class ArgumentSubmitted(_BaseEvent):
    kind: Literal["argument_submitted"] = "argument_submitted"
    argument: Argument
    submitted_at: datetime = Field(default_factory=datetime.now)


class DecisionResolved(_BaseEvent):
    kind: Literal["decision_resolved"] = "decision_resolved"
    decision: Decision
    arguments: list[Argument]
    resolved_at: datetime = Field(default_factory=datetime.now)


class DebateAbandoned(_BaseEvent):
    kind: Literal["debate_abandoned"] = "debate_abandoned"
    reason: str = Field(min_length=1)
    abandoned_at: datetime = Field(default_factory=datetime.now)


DebateEvent = Annotated[
    DebateStarted | ArgumentSubmitted | DecisionResolved | DebateAbandoned,
    Field(discriminator="kind"),
]

DebateEventAdapter: TypeAdapter[DebateEvent] = TypeAdapter(DebateEvent)

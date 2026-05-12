"""Council entities — debate primitives.

`Argument` and `SubtaskBrief` are the domain inputs/outputs of a council
debate. The event vocabulary (`DebateEvent` discriminated union) lives in
`domain/value_objects/council_events.py` since events are immutable
value objects with no identity beyond their data.

Spec: `specs/council-pilot/spec.md` (FR-3, FR-4).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType


class Argument(BaseModel):
    """One engine's case for taking a subtask."""

    engine: AgentEngineType
    capability_claim: str = Field(min_length=1)
    cost_claim: str = Field(min_length=1)
    risk_claim: str = Field(min_length=1)
    recommended_approach: str = Field(min_length=1)


class SubtaskBrief(BaseModel):
    """The unit a council debates over."""

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    task_type: TaskType

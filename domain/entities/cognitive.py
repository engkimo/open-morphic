"""Cognitive entities for the Unified Cognitive Layer (UCL).

Decision — WHY a choice was made (audit trail for reasoning).
AgentAction — WHAT an agent did (audit trail for execution).
SharedTaskState — cross-agent task awareness (companion to TaskEntity).
AgentAffinityScore — engine-topic fitness score.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects.agent_engine import AgentEngineType


class Decision(BaseModel):
    """A recorded decision with rationale — WHY a choice was made."""

    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str = Field(min_length=1)
    rationale: str = ""
    agent_engine: AgentEngineType
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=datetime.now)


class AgentAction(BaseModel):
    """Audit trail of which agent did what."""

    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_engine: AgentEngineType
    action_type: str = Field(min_length=1)  # execute, plan, review, handoff, ...
    summary: str = ""
    cost_usd: float = Field(default=0.0, ge=0.0)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    timestamp: datetime = Field(default_factory=datetime.now)


class SharedTaskState(BaseModel):
    """Cross-agent task awareness — companion to TaskEntity, linked by task_id.

    Tracks decisions, artifacts, blockers, and the full agent action history
    so any engine can pick up where another left off.
    """

    model_config = ConfigDict(strict=True, validate_assignment=True)

    task_id: str = Field(min_length=1)
    decisions: list[Decision] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    agent_history: list[AgentAction] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def add_decision(self, decision: Decision) -> None:
        """Append a decision and bump updated_at."""
        self.decisions.append(decision)
        self.updated_at = datetime.now()

    def add_action(self, action: AgentAction) -> None:
        """Append an agent action and bump updated_at."""
        self.agent_history.append(action)
        self.updated_at = datetime.now()

    def add_artifact(self, key: str, value: str) -> None:
        """Add or overwrite an artifact and bump updated_at."""
        self.artifacts[key] = value
        self.updated_at = datetime.now()

    def add_blocker(self, blocker: str) -> None:
        """Add a blocker if not already present."""
        if blocker not in self.blockers:
            self.blockers.append(blocker)
            self.updated_at = datetime.now()

    def remove_blocker(self, blocker: str) -> None:
        """Remove a blocker if present."""
        if blocker in self.blockers:
            self.blockers.remove(blocker)
            self.updated_at = datetime.now()

    @property
    def last_agent(self) -> AgentEngineType | None:
        """Return the engine of the most recent action, or None."""
        if not self.agent_history:
            return None
        return self.agent_history[-1].agent_engine

    @property
    def total_cost_usd(self) -> float:
        """Sum of all action costs."""
        return sum(a.cost_usd for a in self.agent_history)


class AgentAffinityScore(BaseModel):
    """Engine-topic fitness score for affinity-aware routing."""

    model_config = ConfigDict(strict=True, validate_assignment=True)

    engine: AgentEngineType
    topic: str = Field(min_length=1)
    familiarity: float = Field(default=0.0, ge=0.0, le=1.0)
    recency: float = Field(default=0.0, ge=0.0, le=1.0)
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    cost_efficiency: float = Field(default=0.0, ge=0.0, le=1.0)
    sample_count: int = Field(default=0, ge=0)
    last_used: datetime | None = None

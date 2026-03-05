"""ExecutionRecord entity — the core learning data for Self-Evolution.

Every task execution produces a record: what was tried, with which model/engine,
whether it succeeded, and how much it cost. This data feeds all 3 evolution levels.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType


class ExecutionRecord(BaseModel):
    """A single execution outcome — the raw material for evolution."""

    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = Field(min_length=1)
    task_type: TaskType
    goal: str = ""
    engine_used: AgentEngineType
    model_used: str = ""
    success: bool = False
    error_message: str | None = None
    cost_usd: float = Field(default=0.0, ge=0.0)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    cache_hit_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    user_rating: float | None = Field(default=None, ge=0.0, le=5.0)
    created_at: datetime = Field(default_factory=datetime.now)

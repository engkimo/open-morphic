"""Plan entity — execution plan with cost estimation. Pure domain."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects.status import PlanStatus


class PlanStep(BaseModel):
    """A single step in an execution plan with cost estimate."""

    model_config = ConfigDict(strict=True)

    subtask_description: str = Field(min_length=1)
    proposed_model: str = Field(default="ollama/qwen3:8b")
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    estimated_tokens: int = Field(default=0, ge=0)
    risk_note: str = ""


class ExecutionPlan(BaseModel):
    """A proposed execution plan awaiting user approval."""

    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str = Field(min_length=1)
    steps: list[PlanStep] = Field(default_factory=list)
    total_estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    status: PlanStatus = PlanStatus.PROPOSED
    task_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)

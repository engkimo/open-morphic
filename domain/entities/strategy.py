"""Strategy entities — learned preferences from execution history.

RecoveryRule: Level 1 tactical — known alternatives for common failures.
ModelPreference: Level 2 strategic — learned model performance per task type.
EnginePreference: Level 2 strategic — learned engine performance per task type.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType


class RecoveryRule(BaseModel):
    """A learned alternative when a tool/model fails."""

    model_config = ConfigDict(strict=True)

    error_pattern: str = Field(min_length=1)
    failed_tool: str = ""
    alternative_tool: str = Field(min_length=1)
    alternative_args: dict[str, Any] = Field(default_factory=dict)
    success_count: int = Field(default=0, ge=0)
    total_attempts: int = Field(default=0, ge=0)

    @property
    def success_rate(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return self.success_count / self.total_attempts


class ModelPreference(BaseModel):
    """Learned model performance for a task type."""

    model_config = ConfigDict(strict=True)

    task_type: TaskType
    model: str = Field(min_length=1)
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_cost_usd: float = Field(default=0.0, ge=0.0)
    avg_duration_seconds: float = Field(default=0.0, ge=0.0)
    sample_count: int = Field(default=0, ge=0)


class EnginePreference(BaseModel):
    """Learned engine performance for a task type."""

    model_config = ConfigDict(strict=True)

    task_type: TaskType
    engine: AgentEngineType
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_cost_usd: float = Field(default=0.0, ge=0.0)
    avg_duration_seconds: float = Field(default=0.0, ge=0.0)
    sample_count: int = Field(default=0, ge=0)

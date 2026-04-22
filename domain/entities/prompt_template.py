"""PromptTemplate entity — versioned system prompt with performance tracking.

Each template has a name (e.g. "planner_system") and a monotonically
increasing version. Performance metrics are updated as the template is
used in task executions.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects.model_tier import TaskType


class PromptTemplate(BaseModel):
    """A versioned system prompt template with performance tracking."""

    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(min_length=1)
    version: int = Field(ge=1)
    content: str = Field(min_length=1)
    task_type: TaskType | None = None

    # Performance metrics (updated via record_outcome)
    success_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    total_cost_usd: float = Field(default=0.0, ge=0.0)
    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def sample_count(self) -> int:
        return self.success_count + self.failure_count

    @property
    def success_rate(self) -> float:
        if self.sample_count == 0:
            return 0.0
        return self.success_count / self.sample_count

    @property
    def avg_cost_usd(self) -> float:
        if self.sample_count == 0:
            return 0.0
        return self.total_cost_usd / self.sample_count

    def record_outcome(self, success: bool, cost_usd: float = 0.0) -> None:
        """Record a task execution outcome for this template."""
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        self.total_cost_usd += cost_usd

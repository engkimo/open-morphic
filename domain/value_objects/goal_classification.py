"""GoalClassification — output of a ``GoalClassifierPort``.

Pure VO: a frozen Pydantic model carrying the chosen planner model plus
observability fields (reason, confidence, classifier latency, cost).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects.planner_model import PlannerModel


class GoalClassification(BaseModel):
    """Classifier verdict for a single goal."""

    model_config = ConfigDict(frozen=True)

    model: PlannerModel
    reason: str = Field(min_length=1, max_length=200)
    confidence: float = Field(ge=0.0, le=1.0)
    latency_ms: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)

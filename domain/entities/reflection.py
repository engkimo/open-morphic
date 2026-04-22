"""ReflectionResult — domain entity for post-execution reflection.

Sprint 35 (TD-163): After executing all visible nodes, the reflection
evaluator assesses whether the goal is fully addressed and suggests
additional nodes if needed — enabling "living fractal" dynamic growth.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReflectionResult(BaseModel):
    """Result of a reflection cycle on completed execution nodes.

    When ``is_satisfied`` is False, ``suggested_descriptions`` contains
    action-oriented descriptions for new nodes that should be spawned
    to fill the gap.
    """

    model_config = ConfigDict(strict=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    plan_id: str = Field(min_length=1)
    is_satisfied: bool = True
    missing_aspects: list[str] = Field(default_factory=list)
    suggested_descriptions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    feedback: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)

    @property
    def spawn_count(self) -> int:
        """Number of new nodes to spawn."""
        return len(self.suggested_descriptions) if not self.is_satisfied else 0

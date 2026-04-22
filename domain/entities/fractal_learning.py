"""Fractal Learning entities — error patterns and successful paths.

Sprint 15.7 (TD-105): Minimal viable learning for the fractal engine.
Records error patterns from failures and successful execution paths
for future planning improvement.

Key entities:
  ErrorPattern — recurring failure pattern extracted from Gate ② failures.
  SuccessfulPath — a validated execution sequence for a goal type.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ErrorPattern(BaseModel):
    """A recurring error pattern extracted from fractal engine failures.

    Captures the context (goal type, node description, nesting level)
    and the failure details (error message, evaluation feedback).
    Used by the planner to avoid repeating known-bad strategies.
    """

    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal_fragment: str = Field(min_length=1)
    node_description: str = Field(min_length=1)
    error_message: str = Field(min_length=1)
    nesting_level: int = Field(default=0, ge=0)
    occurrence_count: int = Field(default=1, ge=1)
    first_seen: datetime = Field(default_factory=datetime.now)
    last_seen: datetime = Field(default_factory=datetime.now)

    def matches(self, goal: str, node_desc: str) -> bool:
        """Check if this pattern matches a given goal+node combination."""
        goal_lower = goal.lower()
        node_lower = node_desc.lower()
        return (
            self.goal_fragment.lower() in goal_lower and self.node_description.lower() in node_lower
        )

    def matches_goal(self, goal: str) -> bool:
        """Check if this pattern is relevant for a given goal.

        Uses character n-gram overlap for robust matching across
        rephrased goals and CJK text where substring matching fails.
        Falls back to substring match for short fragments.
        """
        return _goal_overlap(self.goal_fragment, goal)

    def increment(self) -> None:
        """Record another occurrence of this pattern."""
        self.occurrence_count += 1
        self.last_seen = datetime.now()


class SuccessfulPath(BaseModel):
    """A validated successful execution path for a goal type.

    Captures the sequence of node descriptions that led to a successful
    outcome. Used by the planner as a reference template for similar goals.
    """

    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal_fragment: str = Field(min_length=1)
    node_descriptions: list[str] = Field(min_length=1)
    nesting_level: int = Field(default=0, ge=0)
    total_cost_usd: float = Field(default=0.0, ge=0.0)
    usage_count: int = Field(default=1, ge=1)
    first_used: datetime = Field(default_factory=datetime.now)
    last_used: datetime = Field(default_factory=datetime.now)

    def matches(self, goal: str) -> bool:
        """Check if this path is relevant for a given goal."""
        return self.goal_fragment.lower() in goal.lower()

    def matches_goal(self, goal: str) -> bool:
        """Check if this path is relevant for a given goal.

        Uses character n-gram overlap for robust matching across
        rephrased goals and CJK text where substring matching fails.
        Falls back to substring match for short fragments.
        """
        return _goal_overlap(self.goal_fragment, goal)

    def increment(self) -> None:
        """Record another usage of this path."""
        self.usage_count += 1
        self.last_used = datetime.now()


# ---------------------------------------------------------------------------
# Shared matching helpers
# ---------------------------------------------------------------------------


def _ngram_set(text: str, n: int = 4) -> set[str]:
    """Generate character n-grams from a string."""
    t = text.lower()
    if len(t) < n:
        return {t} if t else set()
    return {t[i : i + n] for i in range(len(t) - n + 1)}


def _goal_overlap(
    fragment: str,
    goal: str,
    *,
    ngram_size: int = 4,
    threshold: float = 0.3,
) -> bool:
    """Check if a goal_fragment is semantically related to a goal.

    Uses character n-gram overlap ratio. Works for Latin and CJK text
    without word segmentation. Falls back to substring match when the
    fragment is very short.
    """
    if not fragment or not goal:
        return False

    frag_lower = fragment.lower()
    goal_lower = goal.lower()

    # Fast path: exact substring match (original behaviour)
    if frag_lower in goal_lower:
        return True

    frag_ngrams = _ngram_set(fragment, ngram_size)
    goal_ngrams = _ngram_set(goal, ngram_size)

    if not frag_ngrams:
        return False

    overlap = len(frag_ngrams & goal_ngrams)
    return (overlap / len(frag_ngrams)) >= threshold

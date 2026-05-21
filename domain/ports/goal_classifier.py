"""GoalClassifierPort — abstraction for goal → planner-model classification.

Domain defines WHAT it needs (route a goal to a `PlannerModel`).
Infrastructure provides HOW (LLM via Anthropic, local Ollama qwen3, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.value_objects.goal_classification import GoalClassification


class GoalClassifierPort(ABC):
    """Port for classifying a goal into a target planner model."""

    @abstractmethod
    async def classify(self, goal: str) -> GoalClassification:
        """Return the classifier verdict for ``goal``.

        Raises:
            ValueError: if ``goal`` is empty or whitespace-only.
        """
        ...

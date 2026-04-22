"""PlannerPort — abstraction over plan generation for the fractal engine.

Sprint 15.1: The Planner generates candidate node sequences from a goal.
Supports both forward (start→goal) and backward (goal→start) generation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.fractal_engine import CandidateNode


class PlannerPort(ABC):
    """Generate candidate node sequences from a goal description."""

    @abstractmethod
    async def generate_candidates(
        self,
        goal: str,
        context: str,
        nesting_level: int,
        direction: str = "forward",
    ) -> list[CandidateNode]:
        """Generate candidate nodes for the given goal.

        Args:
            goal: The objective to plan for.
            context: Accumulated context from parent levels.
            nesting_level: Current recursion depth (0 = scenario level).
            direction: "forward" (start→goal) or "backward" (goal→start).

        Returns:
            List of CandidateNode with initial scores. All start as VISIBLE;
            Gate ① will prune/demote as needed.
        """
        ...

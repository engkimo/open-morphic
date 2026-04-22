"""ReflectionEvaluatorPort — post-plan-execution reflection gate.

Sprint 35 (TD-163): After all visible nodes are executed, assess whether
the overall goal is fully addressed. If not, suggest new nodes to spawn.
This is the "living fractal" feedback loop that enables dynamic growth.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.fractal_engine import PlanNode
from domain.entities.reflection import ReflectionResult


class ReflectionEvaluatorPort(ABC):
    """Reflection evaluator — assesses plan completeness after execution."""

    @abstractmethod
    async def reflect(
        self,
        goal: str,
        completed_nodes: list[PlanNode],
        nesting_level: int,
    ) -> ReflectionResult:
        """Evaluate whether the completed nodes fully satisfy the goal.

        Args:
            goal: The original goal the plan was designed to achieve.
            completed_nodes: All nodes executed so far at this level.
            nesting_level: Current recursion depth.

        Returns:
            ReflectionResult indicating satisfaction or suggested expansions.
        """
        ...

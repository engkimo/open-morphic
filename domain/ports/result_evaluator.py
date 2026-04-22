"""ResultEvaluatorPort — Gate ② abstraction for post-execution evaluation.

Sprint 15.1: Evaluates execution output against goal alignment, accuracy,
and validity. Decides: OK (advance), RETRY (re-execute), REPLAN (revise).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.fractal_engine import PlanNode, ResultEvaluation


class ResultEvaluatorPort(ABC):
    """Post-execution result evaluation — Gate ② of the fractal engine."""

    @abstractmethod
    async def evaluate(
        self,
        node: PlanNode,
        goal: str,
        result: str,
    ) -> ResultEvaluation:
        """Evaluate the execution result of a plan node.

        Args:
            node: The executed plan node.
            goal: The original goal for alignment checking.
            result: The execution output to evaluate.

        Returns:
            ResultEvaluation with OK/RETRY/REPLAN decision.
        """
        ...

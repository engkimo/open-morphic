"""PlanEvaluatorPort — Gate ① abstraction for Multi-LLM plan evaluation.

Sprint 15.1: External evaluation of generated plans by multiple LLMs or
evaluation personas. Axes: completeness, feasibility, safety.
Approved plans proceed to execution; rejected plans return to Planner.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.fractal_engine import ExecutionPlan, PlanEvaluation


class PlanEvaluatorPort(ABC):
    """Multi-LLM plan evaluation — Gate ① of the fractal engine."""

    @abstractmethod
    async def evaluate(
        self,
        plan: ExecutionPlan,
        goal: str,
    ) -> PlanEvaluation:
        """Evaluate a proposed execution plan.

        Args:
            plan: The execution plan to evaluate.
            goal: The original goal for alignment checking.

        Returns:
            PlanEvaluation with per-axis scores and approve/reject decision.
        """
        ...

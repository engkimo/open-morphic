"""FailurePropagator — level N → level N-1 failure bubbling logic.

Sprint 15.1: Result Eval failures at level N report to level N-1.
If level N-1 cannot compensate, it bubbles to N-2, and so on until
a level absorbs the failure via replanning or it surfaces to scenario level.
No I/O, no external dependencies. Stateless utility functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.entities.fractal_engine import PlanNode, ResultEvaluation

from domain.value_objects.fractal_engine import ResultEvalDecision


@dataclass(frozen=True)
class PropagationReport:
    """Report describing a failure that must propagate to parent level."""

    node_id: str
    node_description: str
    nesting_level: int
    decision: ResultEvalDecision
    feedback: str
    retries_exhausted: bool
    overall_score: float


class FailurePropagator:
    """Pure functions for failure propagation across nesting levels."""

    @staticmethod
    def should_propagate(
        evaluation: ResultEvaluation,
        retries_exhausted: bool,
    ) -> bool:
        """Determine if a failure should propagate to the parent level.

        Propagation occurs when:
        1. Gate ② says REPLAN (node-level fix insufficient), OR
        2. Gate ② says RETRY but all retries are exhausted.

        OK decisions never propagate.
        """
        if evaluation.decision == ResultEvalDecision.OK:
            return False
        if evaluation.decision == ResultEvalDecision.REPLAN:
            return True
        return evaluation.decision == ResultEvalDecision.RETRY and retries_exhausted

    @staticmethod
    def create_report(
        node: PlanNode,
        evaluation: ResultEvaluation,
        retries_exhausted: bool,
    ) -> PropagationReport:
        """Create a failure report for the parent level."""
        return PropagationReport(
            node_id=node.id,
            node_description=node.description,
            nesting_level=node.nesting_level,
            decision=evaluation.decision,
            feedback=evaluation.feedback,
            retries_exhausted=retries_exhausted,
            overall_score=evaluation.overall_score,
        )

    @staticmethod
    def can_absorb(
        report: PropagationReport,
        has_conditional_fallbacks: bool,
    ) -> bool:
        """Determine if the current level can absorb a propagated failure.

        A level can absorb a failure if:
        1. There are conditional fallback nodes available, OR
        2. The failure is a RETRY (can be replanned locally).

        REPLAN without fallbacks must propagate further up.
        """
        if has_conditional_fallbacks:
            return True
        return report.decision == ResultEvalDecision.RETRY

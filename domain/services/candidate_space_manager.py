"""CandidateSpaceManager — pure logic for iceberg candidate space management.

Sprint 15.1: At each node transition, the engine generates multiple candidate
nodes. This service manages selection, pruning, and conditional activation.
No I/O, no external dependencies. Stateless utility functions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.entities.fractal_engine import CandidateNode, PlanEvaluation

from domain.value_objects.fractal_engine import NodeState, PlanEvalDecision

logger = logging.getLogger(__name__)


class CandidateSpaceManager:
    """Pure functions for iceberg candidate space operations."""

    @staticmethod
    def select_visible(
        candidates: list[CandidateNode],
        top_k: int = 1,
    ) -> tuple[list[CandidateNode], list[CandidateNode]]:
        """Select top-k scoring candidates as VISIBLE; rest become PRUNED.

        Returns:
            (selected, pruned) — two disjoint lists.
        """
        sorted_candidates = sorted(candidates, key=lambda c: c.score, reverse=True)
        selected = sorted_candidates[:top_k]
        pruned = sorted_candidates[top_k:]

        for c in selected:
            c.state = NodeState.VISIBLE
        for c in pruned:
            if c.state == NodeState.VISIBLE:
                c.state = NodeState.PRUNED
                c.prune_reason = "Below top-k score threshold"

        return selected, pruned

    @staticmethod
    def apply_evaluation(
        candidates: list[CandidateNode],
        evaluation: PlanEvaluation,
        min_score: float = 0.5,
    ) -> list[CandidateNode]:
        """Apply Gate ① evaluation: prune candidates below min_score.

        If the overall plan is rejected, all VISIBLE candidates are pruned.
        Otherwise, only individual low-scoring candidates are pruned.

        Returns:
            List of candidates that were pruned by this operation.
        """
        newly_pruned: list[CandidateNode] = []

        if evaluation.decision == PlanEvalDecision.REJECTED:
            for c in candidates:
                if c.state == NodeState.VISIBLE:
                    c.state = NodeState.PRUNED
                    c.prune_reason = f"Plan rejected: {evaluation.feedback}"
                    newly_pruned.append(c)
            return newly_pruned

        for c in candidates:
            if c.state == NodeState.VISIBLE and c.score < min_score:
                c.state = NodeState.PRUNED
                c.prune_reason = f"Score {c.score:.2f} below threshold {min_score:.2f}"
                newly_pruned.append(c)
                logger.debug(
                    "Pruned candidate '%s' (score=%.2f < %.2f)",
                    c.node.description,
                    c.score,
                    min_score,
                )

        return newly_pruned

    @staticmethod
    def activate_conditional(
        candidates: list[CandidateNode],
        triggered_condition: str,
    ) -> list[CandidateNode]:
        """Activate CONDITIONAL nodes whose activation_condition matches.

        Matching is case-insensitive substring match on condition text.

        Returns:
            List of candidates that were activated (state changed to VISIBLE).
        """
        activated: list[CandidateNode] = []
        trigger_lower = triggered_condition.lower()

        for c in candidates:
            if c.state != NodeState.CONDITIONAL:
                continue
            if c.activation_condition and trigger_lower in c.activation_condition.lower():
                c.state = NodeState.VISIBLE
                activated.append(c)
                logger.debug(
                    "Activated conditional node '%s' on condition '%s'",
                    c.node.description,
                    triggered_condition,
                )

        return activated

    @staticmethod
    def mark_failed(
        candidate: CandidateNode,
        reason: str,
    ) -> None:
        """Mark a candidate as FAILED after Gate ② declares failure."""
        candidate.state = NodeState.FAILED
        candidate.failure_reason = reason

    @staticmethod
    def get_visible(candidates: list[CandidateNode]) -> list[CandidateNode]:
        """Return only VISIBLE candidates."""
        return [c for c in candidates if c.state == NodeState.VISIBLE]

    @staticmethod
    def get_fallback_candidates(
        candidates: list[CandidateNode],
    ) -> list[CandidateNode]:
        """Return CONDITIONAL candidates that could serve as fallbacks.

        Sorted by score descending (best fallback first).
        """
        conditional = [c for c in candidates if c.state == NodeState.CONDITIONAL]
        return sorted(conditional, key=lambda c: c.score, reverse=True)

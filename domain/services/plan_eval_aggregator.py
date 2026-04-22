"""PlanEvalAggregator — pure aggregation logic for Gate ① evaluations.

Sprint 15.3: Aggregates multiple PlanEvaluation results from different LLMs
into a single consensus evaluation. Weighted average across axes, threshold-
based approval/rejection. No I/O, no external dependencies.
"""

from __future__ import annotations

from datetime import datetime

from domain.entities.fractal_engine import PlanEvaluation
from domain.value_objects.fractal_engine import PlanEvalDecision


class PlanEvalAggregator:
    """Pure functions for multi-evaluator plan score aggregation."""

    @staticmethod
    def aggregate(
        evaluations: list[PlanEvaluation],
        min_score: float = 0.5,
        axis_weights: dict[str, float] | None = None,
    ) -> PlanEvaluation:
        """Aggregate multiple evaluations into one consensus evaluation.

        Args:
            evaluations: Individual evaluator results.
            min_score: Minimum overall_score for APPROVED decision.
            axis_weights: Optional per-axis weights {"completeness": w, ...}.
                          Defaults to equal weights (1.0 each).

        Returns:
            Single PlanEvaluation with averaged scores and consensus decision.
        """
        if not evaluations:
            return PlanEvaluation(
                plan_id="unknown",
                evaluator_model="aggregated(0)",
                decision=PlanEvalDecision.REJECTED,
                feedback="No evaluations provided",
                timestamp=datetime.now(),
            )

        weights = axis_weights or {
            "completeness": 1.0,
            "feasibility": 1.0,
            "safety": 1.0,
        }

        avg_completeness = _weighted_mean(
            [e.completeness for e in evaluations],
            [1.0] * len(evaluations),
        )
        avg_feasibility = _weighted_mean(
            [e.feasibility for e in evaluations],
            [1.0] * len(evaluations),
        )
        avg_safety = _weighted_mean(
            [e.safety for e in evaluations],
            [1.0] * len(evaluations),
        )

        overall = _weighted_mean(
            [avg_completeness, avg_feasibility, avg_safety],
            [
                weights.get("completeness", 1.0),
                weights.get("feasibility", 1.0),
                weights.get("safety", 1.0),
            ],
        )

        decision = PlanEvalDecision.APPROVED if overall >= min_score else PlanEvalDecision.REJECTED

        feedback = _merge_feedback(evaluations, decision)

        return PlanEvaluation(
            plan_id=evaluations[0].plan_id,
            evaluator_model=f"aggregated({len(evaluations)})",
            completeness=round(avg_completeness, 4),
            feasibility=round(avg_feasibility, 4),
            safety=round(avg_safety, 4),
            overall_score=round(overall, 4),
            decision=decision,
            feedback=feedback,
            timestamp=datetime.now(),
        )


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    """Compute weighted arithmetic mean. Returns 0.0 for empty inputs."""
    if not values or not weights:
        return 0.0
    total_weight = sum(weights)
    if total_weight == 0.0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights, strict=True)) / total_weight


def _merge_feedback(
    evaluations: list[PlanEvaluation],
    decision: PlanEvalDecision,
) -> str:
    """Combine feedback from all evaluators into a single string."""
    parts: list[str] = []
    for i, e in enumerate(evaluations):
        if e.feedback:
            label = e.evaluator_model or f"evaluator-{i}"
            parts.append(f"[{label}] {e.feedback}")
    summary = "; ".join(parts) if parts else "No feedback"
    return f"{decision.value}: {summary}"

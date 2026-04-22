"""ResultEvalDecisionMaker — pure score-to-decision logic for Gate ②.

Sprint 15.4: Converts ResultEvaluation scores into OK/RETRY/REPLAN decisions.
Weighted average across axes, configurable thresholds per AD-4:
  OK     >= ok_threshold (default 0.7)
  RETRY  >= retry_threshold and < ok_threshold (default 0.4-0.7)
  REPLAN <  retry_threshold (default < 0.4)

No I/O, no external dependencies — pure domain service.
"""

from __future__ import annotations

from datetime import datetime

from domain.entities.fractal_engine import ResultEvaluation
from domain.value_objects.fractal_engine import ResultEvalDecision


class ResultEvalDecisionMaker:
    """Pure functions for score-to-decision conversion and multi-eval aggregation."""

    @staticmethod
    def decide(
        evaluation: ResultEvaluation,
        ok_threshold: float = 0.7,
        retry_threshold: float = 0.4,
        axis_weights: dict[str, float] | None = None,
    ) -> ResultEvaluation:
        """Apply thresholds to an evaluation and set the decision.

        Args:
            evaluation: Raw evaluation with scores (decision may be unset).
            ok_threshold: Minimum overall_score for OK decision.
            retry_threshold: Minimum overall_score for RETRY (below this → REPLAN).
            axis_weights: Optional per-axis weights {"accuracy": w, ...}.
                          Defaults to equal weights (1.0 each).

        Returns:
            New ResultEvaluation with overall_score recalculated and decision set.
        """
        weights = axis_weights or {
            "accuracy": 1.0,
            "validity": 1.0,
            "goal_alignment": 1.0,
        }

        raw_overall = _weighted_mean(
            [evaluation.accuracy, evaluation.validity, evaluation.goal_alignment],
            [
                weights.get("accuracy", 1.0),
                weights.get("validity", 1.0),
                weights.get("goal_alignment", 1.0),
            ],
        )
        overall = round(raw_overall, 4)

        decision = _score_to_decision(overall, ok_threshold, retry_threshold)

        return ResultEvaluation(
            node_id=evaluation.node_id,
            decision=decision,
            accuracy=evaluation.accuracy,
            validity=evaluation.validity,
            goal_alignment=evaluation.goal_alignment,
            overall_score=overall,
            feedback=evaluation.feedback,
            timestamp=evaluation.timestamp,
        )

    @staticmethod
    def aggregate(
        evaluations: list[ResultEvaluation],
        ok_threshold: float = 0.7,
        retry_threshold: float = 0.4,
        axis_weights: dict[str, float] | None = None,
    ) -> ResultEvaluation:
        """Aggregate multiple result evaluations into a single consensus.

        Args:
            evaluations: Individual evaluator results.
            ok_threshold: Minimum overall_score for OK decision.
            retry_threshold: Minimum overall_score for RETRY.
            axis_weights: Optional per-axis weights.

        Returns:
            Single ResultEvaluation with averaged scores and consensus decision.
        """
        if not evaluations:
            return ResultEvaluation(
                node_id="unknown",
                decision=ResultEvalDecision.REPLAN,
                feedback="No evaluations provided",
                timestamp=datetime.now(),
            )

        avg_accuracy = _simple_mean([e.accuracy for e in evaluations])
        avg_validity = _simple_mean([e.validity for e in evaluations])
        avg_goal_alignment = _simple_mean([e.goal_alignment for e in evaluations])

        raw = ResultEvaluation(
            node_id=evaluations[0].node_id,
            accuracy=round(avg_accuracy, 4),
            validity=round(avg_validity, 4),
            goal_alignment=round(avg_goal_alignment, 4),
            feedback=_merge_feedback(evaluations),
            timestamp=datetime.now(),
        )

        return ResultEvalDecisionMaker.decide(
            raw,
            ok_threshold=ok_threshold,
            retry_threshold=retry_threshold,
            axis_weights=axis_weights,
        )


def _score_to_decision(
    overall: float,
    ok_threshold: float,
    retry_threshold: float,
) -> ResultEvalDecision:
    """Map an overall score to a Gate ② decision."""
    if overall >= ok_threshold:
        return ResultEvalDecision.OK
    if overall >= retry_threshold:
        return ResultEvalDecision.RETRY
    return ResultEvalDecision.REPLAN


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    """Compute weighted arithmetic mean. Returns 0.0 for empty inputs."""
    if not values or not weights:
        return 0.0
    total_weight = sum(weights)
    if total_weight == 0.0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights, strict=True)) / total_weight


def _simple_mean(values: list[float]) -> float:
    """Compute arithmetic mean. Returns 0.0 for empty list."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _merge_feedback(evaluations: list[ResultEvaluation]) -> str:
    """Combine feedback from all evaluators."""
    parts: list[str] = []
    for i, e in enumerate(evaluations):
        if e.feedback:
            parts.append(f"[eval-{i}] {e.feedback}")
    return "; ".join(parts) if parts else "No feedback"

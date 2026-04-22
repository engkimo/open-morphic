"""Tests for PlanEvalAggregator — pure aggregation logic for Gate ①.

Sprint 15.3: ~10 tests covering weighted averaging, threshold-based
decisions, edge cases (empty, single, multi), and feedback merging.
"""

from __future__ import annotations

import pytest

from domain.entities.fractal_engine import PlanEvaluation
from domain.services.plan_eval_aggregator import (
    PlanEvalAggregator,
    _weighted_mean,
)
from domain.value_objects.fractal_engine import PlanEvalDecision

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _eval(
    plan_id: str = "plan-1",
    model: str = "test-model",
    completeness: float = 0.8,
    feasibility: float = 0.7,
    safety: float = 1.0,
    overall: float = 0.0,
    feedback: str = "",
    decision: PlanEvalDecision = PlanEvalDecision.APPROVED,
) -> PlanEvaluation:
    return PlanEvaluation(
        plan_id=plan_id,
        evaluator_model=model,
        completeness=completeness,
        feasibility=feasibility,
        safety=safety,
        overall_score=overall or round((completeness + feasibility + safety) / 3, 4),
        decision=decision,
        feedback=feedback,
    )


# ===================================================================
# TestAggregate
# ===================================================================


class TestAggregate:
    """Core aggregation behavior."""

    def test_single_evaluation_passes_through(self) -> None:
        evals = [_eval(completeness=0.8, feasibility=0.7, safety=1.0)]

        result = PlanEvalAggregator.aggregate(evals, min_score=0.5)

        assert result.completeness == 0.8
        assert result.feasibility == 0.7
        assert result.safety == 1.0
        assert result.decision == PlanEvalDecision.APPROVED

    def test_multiple_evaluations_averaged(self) -> None:
        evals = [
            _eval(model="model-a", completeness=0.8, feasibility=0.6, safety=1.0),
            _eval(model="model-b", completeness=0.6, feasibility=0.8, safety=0.8),
        ]

        result = PlanEvalAggregator.aggregate(evals, min_score=0.5)

        assert result.completeness == pytest.approx(0.7, abs=0.01)
        assert result.feasibility == pytest.approx(0.7, abs=0.01)
        assert result.safety == pytest.approx(0.9, abs=0.01)
        assert result.evaluator_model == "aggregated(2)"
        assert result.decision == PlanEvalDecision.APPROVED

    def test_three_evaluators_averaged(self) -> None:
        evals = [
            _eval(completeness=0.9, feasibility=0.9, safety=0.9),
            _eval(completeness=0.6, feasibility=0.6, safety=0.6),
            _eval(completeness=0.3, feasibility=0.3, safety=0.3),
        ]

        result = PlanEvalAggregator.aggregate(evals, min_score=0.5)

        assert result.completeness == pytest.approx(0.6, abs=0.01)
        assert result.feasibility == pytest.approx(0.6, abs=0.01)
        assert result.safety == pytest.approx(0.6, abs=0.01)
        assert result.overall_score == pytest.approx(0.6, abs=0.01)
        assert result.decision == PlanEvalDecision.APPROVED

    def test_plan_id_from_first_evaluation(self) -> None:
        evals = [
            _eval(plan_id="plan-abc"),
            _eval(plan_id="plan-xyz"),
        ]

        result = PlanEvalAggregator.aggregate(evals)

        assert result.plan_id == "plan-abc"


# ===================================================================
# TestThreshold
# ===================================================================


class TestThreshold:
    """Threshold-based approval/rejection."""

    def test_exactly_at_threshold_is_approved(self) -> None:
        """overall == min_score → APPROVED."""
        evals = [_eval(completeness=0.5, feasibility=0.5, safety=0.5)]

        result = PlanEvalAggregator.aggregate(evals, min_score=0.5)

        assert result.decision == PlanEvalDecision.APPROVED

    def test_below_threshold_is_rejected(self) -> None:
        evals = [_eval(completeness=0.3, feasibility=0.3, safety=0.3)]

        result = PlanEvalAggregator.aggregate(evals, min_score=0.5)

        assert result.overall_score == pytest.approx(0.3, abs=0.01)
        assert result.decision == PlanEvalDecision.REJECTED

    def test_custom_min_score(self) -> None:
        evals = [_eval(completeness=0.6, feasibility=0.6, safety=0.6)]

        approved = PlanEvalAggregator.aggregate(evals, min_score=0.5)
        rejected = PlanEvalAggregator.aggregate(evals, min_score=0.7)

        assert approved.decision == PlanEvalDecision.APPROVED
        assert rejected.decision == PlanEvalDecision.REJECTED


# ===================================================================
# TestEdgeCases
# ===================================================================


class TestEdgeCases:
    """Edge cases and empty inputs."""

    def test_empty_evaluations_returns_rejected(self) -> None:
        result = PlanEvalAggregator.aggregate([], min_score=0.5)

        assert result.decision == PlanEvalDecision.REJECTED
        assert result.plan_id == "unknown"
        assert "No evaluations" in result.feedback

    def test_all_perfect_scores(self) -> None:
        evals = [_eval(completeness=1.0, feasibility=1.0, safety=1.0)]

        result = PlanEvalAggregator.aggregate(evals, min_score=0.5)

        assert result.overall_score == pytest.approx(1.0, abs=0.01)
        assert result.decision == PlanEvalDecision.APPROVED

    def test_all_zero_scores(self) -> None:
        evals = [_eval(completeness=0.0, feasibility=0.0, safety=0.0)]

        result = PlanEvalAggregator.aggregate(evals, min_score=0.5)

        assert result.overall_score == pytest.approx(0.0, abs=0.01)
        assert result.decision == PlanEvalDecision.REJECTED


# ===================================================================
# TestAxisWeights
# ===================================================================


class TestAxisWeights:
    """Custom axis weighting."""

    def test_safety_heavy_weighting(self) -> None:
        """Safety weight 3x → low safety drags overall down."""
        evals = [_eval(completeness=0.9, feasibility=0.9, safety=0.2)]

        result = PlanEvalAggregator.aggregate(
            evals,
            min_score=0.5,
            axis_weights={"completeness": 1.0, "feasibility": 1.0, "safety": 3.0},
        )

        # overall = (0.9*1 + 0.9*1 + 0.2*3) / 5 = 2.4/5 = 0.48
        assert result.overall_score == pytest.approx(0.48, abs=0.01)
        assert result.decision == PlanEvalDecision.REJECTED

    def test_equal_weights_default(self) -> None:
        evals = [_eval(completeness=0.6, feasibility=0.6, safety=0.6)]

        result = PlanEvalAggregator.aggregate(evals, min_score=0.5)

        assert result.overall_score == pytest.approx(0.6, abs=0.01)


# ===================================================================
# TestFeedback
# ===================================================================


class TestFeedback:
    """Feedback merging from multiple evaluators."""

    def test_feedback_includes_model_labels(self) -> None:
        evals = [
            _eval(model="ollama", feedback="Looks good"),
            _eval(model="claude", feedback="Missing error handling"),
        ]

        result = PlanEvalAggregator.aggregate(evals)

        assert "[ollama]" in result.feedback
        assert "[claude]" in result.feedback
        assert "Looks good" in result.feedback
        assert "Missing error handling" in result.feedback

    def test_empty_feedback_handled(self) -> None:
        evals = [_eval(feedback="")]

        result = PlanEvalAggregator.aggregate(evals)

        assert "No feedback" in result.feedback


# ===================================================================
# TestWeightedMean (module-level helper)
# ===================================================================


class TestWeightedMean:
    """Unit tests for _weighted_mean helper."""

    def test_equal_weights(self) -> None:
        assert _weighted_mean([0.8, 0.6], [1.0, 1.0]) == pytest.approx(0.7)

    def test_unequal_weights(self) -> None:
        # (0.8*2 + 0.4*1) / 3 = 2.0/3 ≈ 0.6667
        assert _weighted_mean([0.8, 0.4], [2.0, 1.0]) == pytest.approx(0.6667, abs=0.001)

    def test_empty_returns_zero(self) -> None:
        assert _weighted_mean([], []) == 0.0

    def test_zero_weights_returns_zero(self) -> None:
        assert _weighted_mean([0.5, 0.5], [0.0, 0.0]) == 0.0

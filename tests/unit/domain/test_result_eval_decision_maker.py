"""Tests for ResultEvalDecisionMaker — pure score-to-decision logic for Gate ②.

Sprint 15.4: ~12 tests covering threshold-based decisions, weighted averaging,
aggregation of multiple evaluations, edge cases, and feedback merging.
"""

from __future__ import annotations

import pytest

from domain.entities.fractal_engine import ResultEvaluation
from domain.services.result_eval_decision_maker import (
    ResultEvalDecisionMaker,
    _score_to_decision,
    _simple_mean,
    _weighted_mean,
)
from domain.value_objects.fractal_engine import ResultEvalDecision

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _eval(
    node_id: str = "node-1",
    accuracy: float = 0.8,
    validity: float = 0.7,
    goal_alignment: float = 0.9,
    feedback: str = "",
) -> ResultEvaluation:
    return ResultEvaluation(
        node_id=node_id,
        accuracy=accuracy,
        validity=validity,
        goal_alignment=goal_alignment,
        overall_score=0.0,
        decision=ResultEvalDecision.OK,  # will be overwritten
        feedback=feedback,
    )


# ===================================================================
# TestDecide — threshold-based decisions
# ===================================================================


class TestDecide:
    """Core decide() behavior with AD-4 thresholds."""

    def test_high_scores_ok(self) -> None:
        result = ResultEvalDecisionMaker.decide(
            _eval(accuracy=0.9, validity=0.8, goal_alignment=0.85),
        )
        assert result.decision == ResultEvalDecision.OK
        assert result.overall_score >= 0.7

    def test_medium_scores_retry(self) -> None:
        result = ResultEvalDecisionMaker.decide(
            _eval(accuracy=0.5, validity=0.5, goal_alignment=0.5),
        )
        assert result.decision == ResultEvalDecision.RETRY
        assert 0.4 <= result.overall_score < 0.7

    def test_low_scores_replan(self) -> None:
        result = ResultEvalDecisionMaker.decide(
            _eval(accuracy=0.2, validity=0.3, goal_alignment=0.1),
        )
        assert result.decision == ResultEvalDecision.REPLAN
        assert result.overall_score < 0.4

    def test_exactly_at_ok_threshold(self) -> None:
        """overall == ok_threshold (0.7) → OK."""
        result = ResultEvalDecisionMaker.decide(
            _eval(accuracy=0.7, validity=0.7, goal_alignment=0.7),
        )
        assert result.decision == ResultEvalDecision.OK

    def test_exactly_at_retry_threshold(self) -> None:
        """overall == retry_threshold (0.4) → RETRY."""
        result = ResultEvalDecisionMaker.decide(
            _eval(accuracy=0.4, validity=0.4, goal_alignment=0.4),
        )
        assert result.decision == ResultEvalDecision.RETRY

    def test_just_below_retry_threshold(self) -> None:
        """overall < retry_threshold → REPLAN."""
        result = ResultEvalDecisionMaker.decide(
            _eval(accuracy=0.3, validity=0.3, goal_alignment=0.39),
        )
        assert result.decision == ResultEvalDecision.REPLAN

    def test_custom_thresholds(self) -> None:
        e = _eval(accuracy=0.6, validity=0.6, goal_alignment=0.6)
        ok_result = ResultEvalDecisionMaker.decide(e, ok_threshold=0.5)
        retry_result = ResultEvalDecisionMaker.decide(e, ok_threshold=0.7)
        replan_result = ResultEvalDecisionMaker.decide(e, ok_threshold=0.8, retry_threshold=0.7)

        assert ok_result.decision == ResultEvalDecision.OK
        assert retry_result.decision == ResultEvalDecision.RETRY
        assert replan_result.decision == ResultEvalDecision.REPLAN

    def test_node_id_preserved(self) -> None:
        result = ResultEvalDecisionMaker.decide(_eval(node_id="abc-123"))
        assert result.node_id == "abc-123"

    def test_feedback_preserved(self) -> None:
        result = ResultEvalDecisionMaker.decide(_eval(feedback="needs improvement"))
        assert result.feedback == "needs improvement"

    def test_scores_preserved(self) -> None:
        result = ResultEvalDecisionMaker.decide(
            _eval(accuracy=0.85, validity=0.75, goal_alignment=0.95),
        )
        assert result.accuracy == 0.85
        assert result.validity == 0.75
        assert result.goal_alignment == 0.95


# ===================================================================
# TestAxisWeights
# ===================================================================


class TestAxisWeights:
    """Custom axis weighting."""

    def test_accuracy_heavy_weighting(self) -> None:
        """Low accuracy with heavy weight → RETRY/REPLAN."""
        result = ResultEvalDecisionMaker.decide(
            _eval(accuracy=0.3, validity=0.9, goal_alignment=0.9),
            axis_weights={"accuracy": 3.0, "validity": 1.0, "goal_alignment": 1.0},
        )
        # overall = (0.3*3 + 0.9*1 + 0.9*1) / 5 = 2.7/5 = 0.54
        assert result.overall_score == pytest.approx(0.54, abs=0.01)
        assert result.decision == ResultEvalDecision.RETRY

    def test_equal_weights_default(self) -> None:
        result = ResultEvalDecisionMaker.decide(
            _eval(accuracy=0.6, validity=0.6, goal_alignment=0.6),
        )
        assert result.overall_score == pytest.approx(0.6, abs=0.01)

    def test_goal_alignment_only_weight(self) -> None:
        """Only goal_alignment matters."""
        result = ResultEvalDecisionMaker.decide(
            _eval(accuracy=0.0, validity=0.0, goal_alignment=0.9),
            axis_weights={"accuracy": 0.0, "validity": 0.0, "goal_alignment": 1.0},
        )
        # This effectively becomes weighted_mean with only goal_alignment having weight
        # But total_weight = 0+0+1 = 1, so overall = 0.9
        assert result.overall_score == pytest.approx(0.9, abs=0.01)
        assert result.decision == ResultEvalDecision.OK


# ===================================================================
# TestAggregate — multi-evaluator aggregation
# ===================================================================


class TestAggregate:
    """Aggregation of multiple result evaluations."""

    def test_single_evaluation_passes_through(self) -> None:
        evals = [_eval(accuracy=0.9, validity=0.8, goal_alignment=0.85)]
        result = ResultEvalDecisionMaker.aggregate(evals)

        assert result.accuracy == pytest.approx(0.9, abs=0.01)
        assert result.validity == pytest.approx(0.8, abs=0.01)
        assert result.goal_alignment == pytest.approx(0.85, abs=0.01)
        assert result.decision == ResultEvalDecision.OK

    def test_two_evaluations_averaged(self) -> None:
        evals = [
            _eval(accuracy=0.8, validity=0.6, goal_alignment=1.0),
            _eval(accuracy=0.6, validity=0.8, goal_alignment=0.8),
        ]
        result = ResultEvalDecisionMaker.aggregate(evals)

        assert result.accuracy == pytest.approx(0.7, abs=0.01)
        assert result.validity == pytest.approx(0.7, abs=0.01)
        assert result.goal_alignment == pytest.approx(0.9, abs=0.01)
        assert result.decision == ResultEvalDecision.OK

    def test_three_evaluations_with_one_low(self) -> None:
        evals = [
            _eval(accuracy=0.9, validity=0.9, goal_alignment=0.9),
            _eval(accuracy=0.8, validity=0.8, goal_alignment=0.8),
            _eval(accuracy=0.1, validity=0.1, goal_alignment=0.1),
        ]
        result = ResultEvalDecisionMaker.aggregate(evals)

        assert result.accuracy == pytest.approx(0.6, abs=0.01)
        assert result.validity == pytest.approx(0.6, abs=0.01)
        assert result.goal_alignment == pytest.approx(0.6, abs=0.01)
        assert result.decision == ResultEvalDecision.RETRY

    def test_node_id_from_first_evaluation(self) -> None:
        evals = [
            _eval(node_id="node-abc"),
            _eval(node_id="node-xyz"),
        ]
        result = ResultEvalDecisionMaker.aggregate(evals)

        assert result.node_id == "node-abc"


# ===================================================================
# TestEdgeCases
# ===================================================================


class TestEdgeCases:
    """Edge cases and empty inputs."""

    def test_empty_evaluations_returns_replan(self) -> None:
        result = ResultEvalDecisionMaker.aggregate([])

        assert result.decision == ResultEvalDecision.REPLAN
        assert result.node_id == "unknown"
        assert "No evaluations" in result.feedback

    def test_all_perfect_scores(self) -> None:
        result = ResultEvalDecisionMaker.decide(
            _eval(accuracy=1.0, validity=1.0, goal_alignment=1.0),
        )
        assert result.overall_score == pytest.approx(1.0, abs=0.01)
        assert result.decision == ResultEvalDecision.OK

    def test_all_zero_scores(self) -> None:
        result = ResultEvalDecisionMaker.decide(
            _eval(accuracy=0.0, validity=0.0, goal_alignment=0.0),
        )
        assert result.overall_score == pytest.approx(0.0, abs=0.01)
        assert result.decision == ResultEvalDecision.REPLAN


# ===================================================================
# TestFeedback
# ===================================================================


class TestFeedback:
    """Feedback merging from multiple evaluators."""

    def test_feedback_merged_with_labels(self) -> None:
        evals = [
            _eval(feedback="Accurate result"),
            _eval(feedback="Missing validation step"),
        ]
        result = ResultEvalDecisionMaker.aggregate(evals)

        assert "[eval-0]" in result.feedback
        assert "[eval-1]" in result.feedback
        assert "Accurate result" in result.feedback
        assert "Missing validation step" in result.feedback

    def test_empty_feedback_handled(self) -> None:
        evals = [_eval(feedback="")]
        result = ResultEvalDecisionMaker.aggregate(evals)

        assert "No feedback" in result.feedback


# ===================================================================
# TestHelpers — module-level helpers
# ===================================================================


class TestHelpers:
    """Unit tests for helper functions."""

    def test_score_to_decision_ok(self) -> None:
        assert _score_to_decision(0.8, 0.7, 0.4) == ResultEvalDecision.OK

    def test_score_to_decision_retry(self) -> None:
        assert _score_to_decision(0.5, 0.7, 0.4) == ResultEvalDecision.RETRY

    def test_score_to_decision_replan(self) -> None:
        assert _score_to_decision(0.3, 0.7, 0.4) == ResultEvalDecision.REPLAN

    def test_weighted_mean_equal(self) -> None:
        assert _weighted_mean([0.8, 0.6], [1.0, 1.0]) == pytest.approx(0.7)

    def test_weighted_mean_unequal(self) -> None:
        assert _weighted_mean([0.8, 0.4], [2.0, 1.0]) == pytest.approx(0.6667, abs=0.001)

    def test_weighted_mean_empty(self) -> None:
        assert _weighted_mean([], []) == 0.0

    def test_weighted_mean_zero_weights(self) -> None:
        assert _weighted_mean([0.5, 0.5], [0.0, 0.0]) == 0.0

    def test_simple_mean(self) -> None:
        assert _simple_mean([0.6, 0.8]) == pytest.approx(0.7)

    def test_simple_mean_empty(self) -> None:
        assert _simple_mean([]) == 0.0

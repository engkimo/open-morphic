"""Tests for fractal engine domain services — Sprint 15.1.

Covers CandidateSpaceManager, FailurePropagator, NestingDepthController.
"""

from __future__ import annotations

from domain.entities.fractal_engine import (
    CandidateNode,
    PlanEvaluation,
    PlanNode,
    ResultEvaluation,
)
from domain.services.candidate_space_manager import CandidateSpaceManager
from domain.services.failure_propagator import FailurePropagator, PropagationReport
from domain.services.nesting_depth_controller import NestingDepthController
from domain.value_objects.fractal_engine import (
    NodeState,
    PlanEvalDecision,
    ResultEvalDecision,
)

# ── CandidateSpaceManager ─────────────────────────────────


class TestCandidateSpaceManager:
    def _make_candidates(self, scores: list[float]) -> list[CandidateNode]:
        return [
            CandidateNode(
                node=PlanNode(description=f"Node {i}"),
                score=s,
            )
            for i, s in enumerate(scores)
        ]

    def test_select_visible_top_1(self):
        candidates = self._make_candidates([0.3, 0.9, 0.5])
        selected, pruned = CandidateSpaceManager.select_visible(candidates, top_k=1)
        assert len(selected) == 1
        assert selected[0].score == 0.9
        assert len(pruned) == 2
        assert all(c.state == NodeState.PRUNED for c in pruned)

    def test_select_visible_top_2(self):
        candidates = self._make_candidates([0.3, 0.9, 0.7])
        selected, pruned = CandidateSpaceManager.select_visible(candidates, top_k=2)
        assert len(selected) == 2
        assert selected[0].score == 0.9
        assert selected[1].score == 0.7
        assert len(pruned) == 1

    def test_apply_evaluation_approved(self):
        candidates = self._make_candidates([0.3, 0.9, 0.5])
        for c in candidates:
            c.state = NodeState.VISIBLE
        evaluation = PlanEvaluation(
            plan_id="p1",
            decision=PlanEvalDecision.APPROVED,
            overall_score=0.8,
        )
        pruned = CandidateSpaceManager.apply_evaluation(candidates, evaluation, min_score=0.4)
        assert len(pruned) == 1
        assert pruned[0].score == 0.3
        assert pruned[0].state == NodeState.PRUNED

    def test_apply_evaluation_rejected_prunes_all(self):
        candidates = self._make_candidates([0.9, 0.8, 0.7])
        for c in candidates:
            c.state = NodeState.VISIBLE
        evaluation = PlanEvaluation(
            plan_id="p1",
            decision=PlanEvalDecision.REJECTED,
            feedback="Bad plan",
        )
        pruned = CandidateSpaceManager.apply_evaluation(candidates, evaluation)
        assert len(pruned) == 3
        assert all(c.state == NodeState.PRUNED for c in pruned)
        assert all("rejected" in (c.prune_reason or "").lower() for c in pruned)

    def test_activate_conditional(self):
        node_a = PlanNode(description="Manual input")
        node_b = PlanNode(description="Image recognition")
        candidates = [
            CandidateNode(
                node=node_a,
                state=NodeState.CONDITIONAL,
                activation_condition="gps_failure",
                score=0.6,
            ),
            CandidateNode(
                node=node_b,
                state=NodeState.CONDITIONAL,
                activation_condition="camera_available",
                score=0.5,
            ),
            CandidateNode(
                node=PlanNode(description="Visible"),
                state=NodeState.VISIBLE,
                score=0.9,
            ),
        ]
        activated = CandidateSpaceManager.activate_conditional(candidates, "GPS_FAILURE")
        assert len(activated) == 1
        assert activated[0].node.description == "Manual input"
        assert activated[0].state == NodeState.VISIBLE

    def test_activate_conditional_no_match(self):
        candidates = [
            CandidateNode(
                node=PlanNode(description="Fallback"),
                state=NodeState.CONDITIONAL,
                activation_condition="timeout",
                score=0.5,
            ),
        ]
        activated = CandidateSpaceManager.activate_conditional(candidates, "gps_failure")
        assert len(activated) == 0

    def test_mark_failed(self):
        candidate = CandidateNode(
            node=PlanNode(description="Step"),
            state=NodeState.VISIBLE,
            score=0.8,
        )
        CandidateSpaceManager.mark_failed(candidate, "Timeout after 30s")
        assert candidate.state == NodeState.FAILED
        assert candidate.failure_reason == "Timeout after 30s"

    def test_get_visible(self):
        candidates = [
            CandidateNode(node=PlanNode(description="A"), state=NodeState.VISIBLE),
            CandidateNode(node=PlanNode(description="B"), state=NodeState.PRUNED),
            CandidateNode(node=PlanNode(description="C"), state=NodeState.VISIBLE),
        ]
        visible = CandidateSpaceManager.get_visible(candidates)
        assert len(visible) == 2

    def test_get_fallback_candidates(self):
        candidates = [
            CandidateNode(
                node=PlanNode(description="Fallback 1"),
                state=NodeState.CONDITIONAL,
                score=0.6,
            ),
            CandidateNode(
                node=PlanNode(description="Fallback 2"),
                state=NodeState.CONDITIONAL,
                score=0.8,
            ),
            CandidateNode(
                node=PlanNode(description="Visible"),
                state=NodeState.VISIBLE,
                score=0.9,
            ),
        ]
        fallbacks = CandidateSpaceManager.get_fallback_candidates(candidates)
        assert len(fallbacks) == 2
        assert fallbacks[0].score == 0.8  # sorted desc


# ── FailurePropagator ──────────────────────────────────────


class TestFailurePropagator:
    def test_ok_never_propagates(self):
        evaluation = ResultEvaluation(
            node_id="n1",
            decision=ResultEvalDecision.OK,
            overall_score=0.9,
        )
        assert FailurePropagator.should_propagate(evaluation, retries_exhausted=False) is False
        assert FailurePropagator.should_propagate(evaluation, retries_exhausted=True) is False

    def test_replan_always_propagates(self):
        evaluation = ResultEvaluation(
            node_id="n1",
            decision=ResultEvalDecision.REPLAN,
            feedback="Fundamentally wrong approach",
        )
        assert FailurePropagator.should_propagate(evaluation, retries_exhausted=False) is True

    def test_retry_propagates_when_exhausted(self):
        evaluation = ResultEvaluation(
            node_id="n1",
            decision=ResultEvalDecision.RETRY,
        )
        assert FailurePropagator.should_propagate(evaluation, retries_exhausted=False) is False
        assert FailurePropagator.should_propagate(evaluation, retries_exhausted=True) is True

    def test_create_report(self):
        node = PlanNode(description="DNN Inference", nesting_level=2)
        evaluation = ResultEvaluation(
            node_id=node.id,
            decision=ResultEvalDecision.REPLAN,
            feedback="Model not available",
            overall_score=0.2,
        )
        report = FailurePropagator.create_report(node, evaluation, retries_exhausted=True)
        assert isinstance(report, PropagationReport)
        assert report.node_id == node.id
        assert report.nesting_level == 2
        assert report.decision == ResultEvalDecision.REPLAN
        assert report.retries_exhausted is True

    def test_can_absorb_with_fallbacks(self):
        report = PropagationReport(
            node_id="n1",
            node_description="Task",
            nesting_level=1,
            decision=ResultEvalDecision.REPLAN,
            feedback="Failed",
            retries_exhausted=True,
            overall_score=0.1,
        )
        assert FailurePropagator.can_absorb(report, has_conditional_fallbacks=True) is True

    def test_cannot_absorb_replan_without_fallbacks(self):
        report = PropagationReport(
            node_id="n1",
            node_description="Task",
            nesting_level=1,
            decision=ResultEvalDecision.REPLAN,
            feedback="Failed",
            retries_exhausted=True,
            overall_score=0.1,
        )
        assert FailurePropagator.can_absorb(report, has_conditional_fallbacks=False) is False

    def test_can_absorb_retry_without_fallbacks(self):
        report = PropagationReport(
            node_id="n1",
            node_description="Task",
            nesting_level=1,
            decision=ResultEvalDecision.RETRY,
            feedback="Try again",
            retries_exhausted=False,
            overall_score=0.4,
        )
        assert FailurePropagator.can_absorb(report, has_conditional_fallbacks=False) is True


# ── NestingDepthController ─────────────────────────────────


class TestNestingDepthController:
    def test_can_expand_within_limit(self):
        assert NestingDepthController.can_expand(0, max_depth=5) is True
        assert NestingDepthController.can_expand(4, max_depth=5) is True

    def test_cannot_expand_at_limit(self):
        assert NestingDepthController.can_expand(5, max_depth=5) is False
        assert NestingDepthController.can_expand(6, max_depth=5) is False

    def test_should_terminate_terminal_node(self):
        is_term, reason = NestingDepthController.should_terminate(nesting_level=1, is_terminal=True)
        assert is_term is True
        assert reason == "node_marked_terminal"

    def test_should_terminate_max_depth(self):
        is_term, reason = NestingDepthController.should_terminate(
            nesting_level=5, is_terminal=False, max_depth=5
        )
        assert is_term is True
        assert reason == "max_depth_reached"

    def test_expandable(self):
        is_term, reason = NestingDepthController.should_terminate(
            nesting_level=2, is_terminal=False, max_depth=5
        )
        assert is_term is False
        assert reason == "expandable"

    def test_check_budget_no_limit(self):
        within, reason = NestingDepthController.check_budget(10.0, budget_usd=0)
        assert within is True
        assert reason == "no_budget_limit"

    def test_check_budget_exhausted(self):
        within, reason = NestingDepthController.check_budget(5.0, budget_usd=5.0)
        assert within is False
        assert reason == "budget_exhausted"

    def test_check_budget_nearly_exhausted(self):
        within, reason = NestingDepthController.check_budget(4.95, budget_usd=5.0)
        assert within is False
        assert reason == "budget_nearly_exhausted"

    def test_check_budget_within(self):
        within, reason = NestingDepthController.check_budget(2.0, budget_usd=5.0)
        assert within is True
        assert reason == "within_budget"

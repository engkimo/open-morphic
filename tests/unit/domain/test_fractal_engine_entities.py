"""Tests for fractal engine domain entities — Sprint 15.1.

Covers PlanNode, CandidateNode, ExecutionPlan, PlanEvaluation, ResultEvaluation.
"""

from __future__ import annotations

import pytest

from domain.entities.fractal_engine import (
    CandidateNode,
    ExecutionPlan,
    PlanEvaluation,
    PlanNode,
    ResultEvaluation,
)
from domain.value_objects.fractal_engine import (
    NodeState,
    PlanEvalDecision,
    ResultEvalDecision,
)
from domain.value_objects.status import PlanStatus, SubTaskStatus

# ── PlanNode ───────────────────────────────────────────────


class TestPlanNode:
    def test_defaults(self):
        node = PlanNode(description="Run tests")
        assert node.nesting_level == 0
        assert node.status == SubTaskStatus.PENDING
        assert node.is_terminal is False
        assert node.retry_count == 0
        assert node.max_retries == 3
        assert node.cost_usd == 0.0
        assert node.parent_node_id is None
        assert node.input_artifacts == {}
        assert node.output_artifacts == {}

    def test_can_retry(self):
        node = PlanNode(description="Task", retry_count=2, max_retries=3)
        assert node.can_retry is True

    def test_cannot_retry_when_exhausted(self):
        node = PlanNode(description="Task", retry_count=3, max_retries=3)
        assert node.can_retry is False

    def test_unique_ids(self):
        a = PlanNode(description="A")
        b = PlanNode(description="B")
        assert a.id != b.id

    def test_nesting_level_validation(self):
        with pytest.raises(ValueError):
            PlanNode(description="X", nesting_level=-1)

    def test_artifacts(self):
        node = PlanNode(
            description="Code",
            output_artifacts={"code": "print('hello')"},
        )
        assert node.output_artifacts["code"] == "print('hello')"


# ── CandidateNode ──────────────────────────────────────────


class TestCandidateNode:
    def test_defaults(self):
        node = PlanNode(description="Step A")
        candidate = CandidateNode(node=node)
        assert candidate.state == NodeState.VISIBLE
        assert candidate.score == 0.0
        assert candidate.prune_reason is None
        assert candidate.failure_reason is None
        assert candidate.activation_condition is None

    def test_conditional_with_activation(self):
        node = PlanNode(description="GPS fallback")
        candidate = CandidateNode(
            node=node,
            state=NodeState.CONDITIONAL,
            activation_condition="gps_failure",
            score=0.7,
        )
        assert candidate.state == NodeState.CONDITIONAL
        assert candidate.activation_condition == "gps_failure"

    def test_pruned_with_reason(self):
        node = PlanNode(description="Low quality")
        candidate = CandidateNode(
            node=node,
            state=NodeState.PRUNED,
            prune_reason="Score too low",
            score=0.2,
        )
        assert candidate.state == NodeState.PRUNED
        assert candidate.prune_reason == "Score too low"


# ── ExecutionPlan ──────────────────────────────────────────


class TestExecutionPlan:
    def _make_plan(self) -> ExecutionPlan:
        nodes = [
            PlanNode(description="Step 1", status=SubTaskStatus.SUCCESS),
            PlanNode(description="Step 2", status=SubTaskStatus.PENDING),
            PlanNode(description="Step 3", status=SubTaskStatus.PENDING),
        ]
        candidates = [
            CandidateNode(node=PlanNode(description="Alt A"), state=NodeState.PRUNED),
            CandidateNode(node=PlanNode(description="Alt B"), state=NodeState.CONDITIONAL),
            CandidateNode(node=PlanNode(description="Alt C"), state=NodeState.FAILED),
        ]
        return ExecutionPlan(
            goal="Build API",
            visible_nodes=nodes,
            candidate_space=candidates,
        )

    def test_visible_count(self):
        plan = self._make_plan()
        assert plan.visible_count == 3

    def test_pruned_count(self):
        plan = self._make_plan()
        assert plan.pruned_count == 1

    def test_conditional_count(self):
        plan = self._make_plan()
        assert plan.conditional_count == 1

    def test_failed_count(self):
        plan = self._make_plan()
        assert plan.failed_count == 1

    def test_get_ready_nodes(self):
        plan = self._make_plan()
        ready = plan.get_ready_nodes()
        assert len(ready) == 2
        assert all(n.status == SubTaskStatus.PENDING for n in ready)

    def test_get_conditional_nodes(self):
        plan = self._make_plan()
        cond = plan.get_conditional_nodes()
        assert len(cond) == 1
        assert cond[0].node.description == "Alt B"

    def test_defaults(self):
        plan = ExecutionPlan(goal="Test")
        assert plan.status == PlanStatus.PROPOSED
        assert plan.nesting_level == 0
        assert plan.parent_plan_id is None
        assert plan.visible_nodes == []
        assert plan.candidate_space == []

    def test_nested_plan(self):
        plan = ExecutionPlan(
            goal="Sub-task",
            nesting_level=2,
            parent_plan_id="parent-plan-id",
            parent_node_id="parent-node-id",
        )
        assert plan.nesting_level == 2
        assert plan.parent_plan_id == "parent-plan-id"


# ── PlanEvaluation ─────────────────────────────────────────


class TestPlanEvaluation:
    def test_approved(self):
        ev = PlanEvaluation(
            plan_id="p1",
            evaluator_model="claude-sonnet-4-6",
            completeness=0.9,
            feasibility=0.8,
            safety=1.0,
            overall_score=0.9,
            decision=PlanEvalDecision.APPROVED,
        )
        assert ev.decision == PlanEvalDecision.APPROVED
        assert ev.overall_score == 0.9

    def test_rejected_with_feedback(self):
        ev = PlanEvaluation(
            plan_id="p2",
            evaluator_model="gpt-4o",
            completeness=0.3,
            feasibility=0.4,
            safety=0.9,
            overall_score=0.4,
            decision=PlanEvalDecision.REJECTED,
            feedback="Missing error handling step",
        )
        assert ev.decision == PlanEvalDecision.REJECTED
        assert "error handling" in ev.feedback

    def test_score_bounds(self):
        with pytest.raises(ValueError):
            PlanEvaluation(plan_id="p3", completeness=1.5)


# ── ResultEvaluation ───────────────────────────────────────


class TestResultEvaluation:
    def test_ok(self):
        ev = ResultEvaluation(
            node_id="n1",
            decision=ResultEvalDecision.OK,
            accuracy=0.95,
            validity=0.9,
            goal_alignment=0.85,
            overall_score=0.9,
        )
        assert ev.decision == ResultEvalDecision.OK

    def test_retry(self):
        ev = ResultEvaluation(
            node_id="n2",
            decision=ResultEvalDecision.RETRY,
            accuracy=0.3,
            validity=0.5,
            goal_alignment=0.4,
            overall_score=0.4,
            feedback="Output incomplete, retry with more context",
        )
        assert ev.decision == ResultEvalDecision.RETRY

    def test_replan(self):
        ev = ResultEvaluation(
            node_id="n3",
            decision=ResultEvalDecision.REPLAN,
            feedback="Approach fundamentally flawed",
        )
        assert ev.decision == ResultEvalDecision.REPLAN

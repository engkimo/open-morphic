"""Tests for Plan entities — Sprint 2-C."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.entities.plan import ExecutionPlan, PlanStep
from domain.value_objects.status import PlanStatus


class TestPlanStep:
    def test_create_minimal(self) -> None:
        step = PlanStep(subtask_description="implement auth")
        assert step.subtask_description == "implement auth"
        assert step.proposed_model == "ollama/qwen3:8b"
        assert step.estimated_cost_usd == 0.0
        assert step.estimated_tokens == 0

    def test_create_with_all_fields(self) -> None:
        step = PlanStep(
            subtask_description="code review",
            proposed_model="claude-sonnet-4-6",
            estimated_cost_usd=0.05,
            estimated_tokens=5000,
            risk_note="May require API key",
        )
        assert step.proposed_model == "claude-sonnet-4-6"
        assert step.estimated_cost_usd == 0.05
        assert step.risk_note == "May require API key"

    def test_empty_description_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PlanStep(subtask_description="")

    def test_negative_cost_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PlanStep(subtask_description="test", estimated_cost_usd=-1.0)


class TestExecutionPlan:
    def test_create_minimal(self) -> None:
        plan = ExecutionPlan(goal="build API")
        assert plan.goal == "build API"
        assert plan.status == PlanStatus.PROPOSED
        assert plan.steps == []
        assert plan.total_estimated_cost_usd == 0.0
        assert plan.task_id is None

    def test_create_with_steps(self) -> None:
        steps = [
            PlanStep(subtask_description="step 1", estimated_cost_usd=0.01),
            PlanStep(subtask_description="step 2", estimated_cost_usd=0.02),
        ]
        plan = ExecutionPlan(
            goal="test plan",
            steps=steps,
            total_estimated_cost_usd=0.03,
        )
        assert len(plan.steps) == 2
        assert plan.total_estimated_cost_usd == 0.03

    def test_status_transition(self) -> None:
        plan = ExecutionPlan(goal="transition test")
        assert plan.status == PlanStatus.PROPOSED
        plan.status = PlanStatus.APPROVED
        assert plan.status == PlanStatus.APPROVED

    def test_empty_goal_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionPlan(goal="")


class TestPlanStatus:
    def test_all_values(self) -> None:
        assert PlanStatus.PROPOSED.value == "proposed"
        assert PlanStatus.APPROVED.value == "approved"
        assert PlanStatus.REJECTED.value == "rejected"
        assert PlanStatus.EXECUTING.value == "executing"
        assert PlanStatus.COMPLETED.value == "completed"

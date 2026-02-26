"""Tests for InteractivePlanUseCase — Sprint 2-C."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from application.use_cases.cost_estimator import CostEstimator
from application.use_cases.interactive_plan import (
    InteractivePlanUseCase,
    PlanAlreadyDecidedError,
    PlanNotFoundError,
)
from domain.entities.task import SubTask
from domain.value_objects.status import PlanStatus
from infrastructure.persistence.in_memory import InMemoryPlanRepository, InMemoryTaskRepository


def _make_use_case(
    subtask_descriptions: list[str] | None = None,
) -> tuple[InteractivePlanUseCase, InMemoryPlanRepository, InMemoryTaskRepository]:
    """Create use case with mocked engine."""
    engine = AsyncMock()
    descriptions = subtask_descriptions or ["step 1", "step 2", "step 3"]
    engine.decompose = AsyncMock(return_value=[SubTask(description=d) for d in descriptions])

    plan_repo = InMemoryPlanRepository()
    task_repo = InMemoryTaskRepository()
    estimator = CostEstimator()

    uc = InteractivePlanUseCase(
        engine=engine,
        cost_estimator=estimator,
        plan_repo=plan_repo,
        task_repo=task_repo,
    )
    return uc, plan_repo, task_repo


class TestCreatePlan:
    @pytest.mark.asyncio
    async def test_creates_proposed_plan(self) -> None:
        uc, plan_repo, _ = _make_use_case()
        plan = await uc.create_plan("build auth system")
        assert plan.status == PlanStatus.PROPOSED
        assert len(plan.steps) == 3
        assert plan.goal == "build auth system"

    @pytest.mark.asyncio
    async def test_local_model_zero_cost(self) -> None:
        uc, _, _ = _make_use_case()
        plan = await uc.create_plan("test", model="ollama/qwen3:8b")
        assert plan.total_estimated_cost_usd == 0.0

    @pytest.mark.asyncio
    async def test_cloud_model_has_cost(self) -> None:
        uc, _, _ = _make_use_case()
        plan = await uc.create_plan("test", model="claude-sonnet-4-6")
        assert plan.total_estimated_cost_usd > 0

    @pytest.mark.asyncio
    async def test_plan_persisted(self) -> None:
        uc, plan_repo, _ = _make_use_case()
        plan = await uc.create_plan("persist test")
        stored = await plan_repo.get_by_id(plan.id)
        assert stored is not None
        assert stored.goal == "persist test"

    @pytest.mark.asyncio
    async def test_fallback_single_subtask(self) -> None:
        """If decompose returns empty, use goal as single step."""
        uc, _, _ = _make_use_case(subtask_descriptions=[])
        # Override to return empty
        uc._engine.decompose = AsyncMock(return_value=[])
        plan = await uc.create_plan("simple goal")
        assert len(plan.steps) == 1
        assert plan.steps[0].subtask_description == "simple goal"


class TestApprovePlan:
    @pytest.mark.asyncio
    async def test_approve_creates_task(self) -> None:
        uc, plan_repo, task_repo = _make_use_case()
        plan = await uc.create_plan("approve test")
        task = await uc.approve_plan(plan.id)
        assert task.goal == "approve test"
        assert len(task.subtasks) == 3

        # Plan updated
        updated_plan = await plan_repo.get_by_id(plan.id)
        assert updated_plan.status == PlanStatus.APPROVED
        assert updated_plan.task_id == task.id

        # Task persisted
        stored_task = await task_repo.get_by_id(task.id)
        assert stored_task is not None

    @pytest.mark.asyncio
    async def test_approve_nonexistent_raises(self) -> None:
        uc, _, _ = _make_use_case()
        with pytest.raises(PlanNotFoundError):
            await uc.approve_plan("nonexistent")

    @pytest.mark.asyncio
    async def test_approve_already_approved_raises(self) -> None:
        uc, _, _ = _make_use_case()
        plan = await uc.create_plan("double approve")
        await uc.approve_plan(plan.id)
        with pytest.raises(PlanAlreadyDecidedError):
            await uc.approve_plan(plan.id)


class TestRejectPlan:
    @pytest.mark.asyncio
    async def test_reject_plan(self) -> None:
        uc, plan_repo, _ = _make_use_case()
        plan = await uc.create_plan("reject test")
        result = await uc.reject_plan(plan.id)
        assert result.status == PlanStatus.REJECTED

    @pytest.mark.asyncio
    async def test_reject_nonexistent_raises(self) -> None:
        uc, _, _ = _make_use_case()
        with pytest.raises(PlanNotFoundError):
            await uc.reject_plan("nonexistent")

    @pytest.mark.asyncio
    async def test_reject_already_rejected_raises(self) -> None:
        uc, _, _ = _make_use_case()
        plan = await uc.create_plan("double reject")
        await uc.reject_plan(plan.id)
        with pytest.raises(PlanAlreadyDecidedError):
            await uc.reject_plan(plan.id)

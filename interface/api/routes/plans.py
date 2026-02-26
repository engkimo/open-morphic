"""Plan endpoints — create, view, approve, reject execution plans."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from interface.api.schemas import (
    CreatePlanRequest,
    ExecutionPlanResponse,
    PlanListResponse,
    TaskResponse,
)

router = APIRouter(prefix="/api/plans", tags=["plans"])


def _container(request: Request):  # noqa: ANN202
    return request.app.state.container


@router.post("", status_code=201, response_model=ExecutionPlanResponse)
async def create_plan(body: CreatePlanRequest, request: Request) -> ExecutionPlanResponse:
    c = _container(request)
    plan = await c.interactive_plan.create_plan(body.goal, model=body.model)
    return ExecutionPlanResponse.from_plan(plan)


@router.get("", response_model=PlanListResponse)
async def list_plans(request: Request) -> PlanListResponse:
    c = _container(request)
    plans = await c.plan_repo.list_all()
    items = [ExecutionPlanResponse.from_plan(p) for p in plans]
    return PlanListResponse(plans=items, count=len(items))


@router.get("/{plan_id}", response_model=ExecutionPlanResponse)
async def get_plan(plan_id: str, request: Request) -> ExecutionPlanResponse:
    c = _container(request)
    plan = await c.plan_repo.get_by_id(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    return ExecutionPlanResponse.from_plan(plan)


@router.post("/{plan_id}/approve", response_model=TaskResponse)
async def approve_plan(plan_id: str, request: Request) -> TaskResponse:
    from application.use_cases.interactive_plan import PlanAlreadyDecidedError, PlanNotFoundError

    c = _container(request)
    try:
        task = await c.interactive_plan.approve_plan(plan_id)
    except PlanNotFoundError:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    except PlanAlreadyDecidedError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Optionally trigger execution
    if c.settings.celery_enabled:
        from infrastructure.queue.tasks import execute_task_worker

        execute_task_worker.delay(task.id)
    return TaskResponse.from_task(task)


@router.post("/{plan_id}/reject", response_model=ExecutionPlanResponse)
async def reject_plan(plan_id: str, request: Request) -> ExecutionPlanResponse:
    from application.use_cases.interactive_plan import PlanAlreadyDecidedError, PlanNotFoundError

    c = _container(request)
    try:
        plan = await c.interactive_plan.reject_plan(plan_id)
    except PlanNotFoundError:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    except PlanAlreadyDecidedError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ExecutionPlanResponse.from_plan(plan)

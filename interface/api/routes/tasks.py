"""Task CRUD endpoints.

Sprint 9.4: Plan-first flow as default.
  - INTERACTIVE mode: POST /api/tasks creates a plan first, returns 202
  - DISABLED mode: POST /api/tasks creates and executes immediately (legacy)
  - AUTO mode: same as INTERACTIVE but simple tasks auto-approve
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from domain.services.task_complexity import TaskComplexityClassifier
from domain.value_objects.task_complexity import TaskComplexity
from interface.api.schemas import (
    CreateTaskRequest,
    ExecutionPlanResponse,
    TaskListResponse,
    TaskResponse,
)
from shared.config import PlanningMode

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _container(request: Request):  # noqa: ANN202
    return request.app.state.container


@router.post("", status_code=201)
async def create_task(
    body: CreateTaskRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> TaskResponse | ExecutionPlanResponse:
    c = _container(request)
    mode = c.settings.planning_mode

    # DISABLED mode — legacy: create & execute immediately
    if mode == PlanningMode.DISABLED:
        return await _create_and_execute(c, body.goal, background_tasks)

    # INTERACTIVE / AUTO mode — plan-first flow
    plan = await c.interactive_plan.create_plan(body.goal)

    # AUTO mode: auto-approve simple tasks
    if mode == PlanningMode.AUTO and c.settings.planning_auto_approve_simple:
        complexity = TaskComplexityClassifier.classify(body.goal)
        if complexity == TaskComplexity.SIMPLE:
            task = await c.interactive_plan.approve_plan(plan.id)
            background_tasks.add_task(c.execute_task.execute, task.id)
            return TaskResponse.from_task(task)

    # Return plan for review (INTERACTIVE, or non-simple AUTO)
    return ExecutionPlanResponse.from_plan(plan)


async def _create_and_execute(
    c,  # noqa: ANN001
    goal: str,
    background_tasks: BackgroundTasks,
) -> TaskResponse:
    """Legacy flow: create task and dispatch execution immediately."""
    task = await c.create_task.execute(goal)
    if c.settings.celery_enabled:
        from infrastructure.queue.tasks import execute_task_worker

        execute_task_worker.delay(task.id)
    else:
        background_tasks.add_task(c.execute_task.execute, task.id)
    return TaskResponse.from_task(task)


@router.get("", response_model=TaskListResponse)
async def list_tasks(request: Request) -> TaskListResponse:
    c = _container(request)
    tasks = await c.task_repo.list_all()
    items = [TaskResponse.from_task(t) for t in tasks]
    return TaskListResponse(tasks=items, count=len(items))


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, request: Request) -> TaskResponse:
    c = _container(request)
    task = await c.task_repo.get_by_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return TaskResponse.from_task(task)


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str, request: Request) -> None:
    c = _container(request)
    task = await c.task_repo.get_by_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    await c.task_repo.delete(task_id)

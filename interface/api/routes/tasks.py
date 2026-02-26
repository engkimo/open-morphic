"""Task CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from interface.api.schemas import (
    CreateTaskRequest,
    TaskListResponse,
    TaskResponse,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _container(request: Request):  # noqa: ANN202
    return request.app.state.container


@router.post("", status_code=201, response_model=TaskResponse)
async def create_task(
    body: CreateTaskRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> TaskResponse:
    c = _container(request)
    task = await c.create_task.execute(body.goal)

    # Dispatch execution: Celery worker or in-process background
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

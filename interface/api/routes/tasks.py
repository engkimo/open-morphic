"""Task CRUD endpoints.

Sprint 9.4: Plan-first flow as default.
  - INTERACTIVE mode: POST /api/tasks creates a plan first, returns 202
  - DISABLED mode: POST /api/tasks creates and executes immediately (legacy)
  - AUTO mode: same as INTERACTIVE but simple tasks auto-approve
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from domain.services.model_preference_extractor import ModelPreferenceExtractor
from domain.services.task_complexity import TaskComplexityClassifier
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.task_complexity import TaskComplexity
from interface.api.schemas import (
    CreateTaskRequest,
    ExecutionPlanResponse,
    TaskListResponse,
    TaskResponse,
)
from shared.config import PlanningMode

logger = logging.getLogger(__name__)

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

    # Parse optional engine override
    engine_type: AgentEngineType | None = None
    if body.engine:
        with contextlib.suppress(ValueError):
            engine_type = AgentEngineType(body.engine)

    logger.info(
        "POST /api/tasks — goal=%r mode=%s engine=%s",
        body.goal[:60], mode, engine_type,
    )

    # Collect per-task fractal overrides (TD-175)
    fractal_overrides: dict[str, int] = {}
    if body.fractal_max_depth is not None:
        fractal_overrides["max_depth"] = body.fractal_max_depth
    if body.fractal_max_concurrent_nodes is not None:
        fractal_overrides["max_concurrent_nodes"] = body.fractal_max_concurrent_nodes
    if body.fractal_throttle_delay_ms is not None:
        fractal_overrides["throttle_delay_ms"] = body.fractal_throttle_delay_ms

    # DISABLED mode — legacy: create & execute immediately
    if mode == PlanningMode.DISABLED:
        logger.info("DISABLED mode — creating and executing immediately")
        return await _create_and_execute(
            c, body.goal, background_tasks, engine_type,
            fractal_overrides=fractal_overrides,
        )

    # INTERACTIVE / AUTO mode — plan-first flow
    plan = await c.interactive_plan.create_plan(body.goal)
    logger.info("Plan created — id=%s steps=%d", plan.id[:8], len(plan.steps))

    # AUTO mode: auto-approve simple tasks AND multi-model goals
    # (user explicitly named models → auto-approve regardless of complexity)
    if mode == PlanningMode.AUTO and c.settings.planning_auto_approve_simple:
        pref = ModelPreferenceExtractor.extract(body.goal)
        complexity = TaskComplexityClassifier.classify(body.goal)
        should_auto = complexity == TaskComplexity.SIMPLE or pref.is_multi_model
        if should_auto:
            logger.info("AUTO mode — SIMPLE task auto-approved")
            task = await c.interactive_plan.approve_plan(plan.id)
            asyncio.create_task(
                _safe_execute(c, task.id, engine_type, fractal_overrides=fractal_overrides)
            )
            return TaskResponse.from_task(task)

    # Return plan for review (INTERACTIVE, or non-simple AUTO)
    logger.info("Returning plan for review — plan_id=%s", plan.id[:8])
    return ExecutionPlanResponse.from_plan(plan)


async def _create_and_execute(
    c,  # noqa: ANN001
    goal: str,
    background_tasks: BackgroundTasks,
    engine_type: AgentEngineType | None = None,
    *,
    fractal_overrides: dict[str, int] | None = None,
) -> TaskResponse:
    """Legacy flow: create task and dispatch execution immediately."""
    task = await c.create_task.execute(goal)
    if c.settings.celery_enabled:
        from infrastructure.queue.tasks import execute_task_worker

        execute_task_worker.delay(task.id)
    else:
        asyncio.create_task(
            _safe_execute(c, task.id, engine_type, fractal_overrides=fractal_overrides)
        )
    return TaskResponse.from_task(task)


async def _safe_execute(
    c,  # noqa: ANN001
    task_id: str,
    engine_type: AgentEngineType | None = None,
    *,
    fractal_overrides: dict[str, int] | None = None,
) -> None:
    """Fire-and-forget task execution — never blocks the event loop."""
    try:
        # TD-156: Goal-level auto-route when no engine specified.
        # Classify the goal to determine the best engine for recording
        # and to surface the routing decision in logs.
        if engine_type is None:
            from domain.services.agent_engine_router import AgentEngineRouter
            from domain.services.subtask_type_classifier import SubtaskTypeClassifier

            task = await c.task_repo.get_by_id(task_id)
            if task:
                inferred = SubtaskTypeClassifier.infer(task.goal)
                engine_type = AgentEngineRouter.select(
                    task_type=inferred,
                    budget=c.settings.default_task_budget_usd,
                )
                logger.info(
                    "Goal auto-route: %r → %s → %s",
                    task.goal[:60],
                    inferred.value,
                    engine_type.value,
                )

        # TD-175: Apply per-task fractal overrides before execution
        if fractal_overrides:
            engine = c.task_engine
            if hasattr(engine, "set_execution_overrides"):
                engine.set_execution_overrides(fractal_overrides)

        et = engine_type or AgentEngineType.OLLAMA
        await c.execute_task.execute(task_id, engine_type=et)
    except Exception:
        logger.exception("Background execution failed: %s", task_id)


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

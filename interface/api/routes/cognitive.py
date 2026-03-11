"""UCL / Cognitive API routes — shared task state, affinity, handoff, insights."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from domain.services.agent_affinity import AgentAffinityScorer
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from interface.api.schemas import (
    AffinityListResponse,
    AffinityScoreResponse,
    HandoffRequestSchema,
    HandoffResponseSchema,
    InsightExtractRequest,
    InsightListResponse,
    InsightResponse,
    SharedTaskStateListResponse,
    SharedTaskStateResponse,
)

router = APIRouter(prefix="/api/cognitive", tags=["cognitive"])


def _container(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.container


# ---------- Shared Task State ----------


@router.get("/state", response_model=SharedTaskStateListResponse)
async def list_states(request: Request) -> SharedTaskStateListResponse:
    """List active shared task states."""
    c = _container(request)
    states = await c.shared_task_state_repo.list_active()
    return SharedTaskStateListResponse(
        states=[SharedTaskStateResponse.from_state(s) for s in states],
        count=len(states),
    )


@router.get("/state/{task_id}", response_model=SharedTaskStateResponse)
async def get_state(task_id: str, request: Request) -> SharedTaskStateResponse:
    """Get shared task state for a specific task."""
    c = _container(request)
    state = await c.shared_task_state_repo.get(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"No shared state for task {task_id}")
    return SharedTaskStateResponse.from_state(state)


@router.delete("/state/{task_id}", status_code=204)
async def delete_state(task_id: str, request: Request) -> None:
    """Delete shared task state."""
    c = _container(request)
    state = await c.shared_task_state_repo.get(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"No shared state for task {task_id}")
    await c.shared_task_state_repo.delete(task_id)


# ---------- Affinity ----------


@router.get("/affinity", response_model=AffinityListResponse)
async def list_affinities(
    request: Request,
    topic: str | None = None,
    engine: str | None = None,
) -> AffinityListResponse:
    """List affinity scores, optionally filtered by topic or engine."""
    c = _container(request)
    if topic:
        scores = await c.affinity_repo.get_by_topic(topic)
    elif engine:
        try:
            engine_type = AgentEngineType(engine)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown engine: {engine}") from None
        scores = await c.affinity_repo.get_by_engine(engine_type)
    else:
        scores = await c.affinity_repo.list_all()

    items = [AffinityScoreResponse.from_affinity(s, AgentAffinityScorer.score(s)) for s in scores]
    return AffinityListResponse(scores=items, count=len(items))


# ---------- Handoff ----------


@router.post("/handoff", response_model=HandoffResponseSchema)
async def handoff_task(body: HandoffRequestSchema, request: Request) -> HandoffResponseSchema:
    """Hand off a task from one engine to another."""
    from application.use_cases.handoff_task import HandoffRequest

    c = _container(request)

    try:
        source = AgentEngineType(body.source_engine)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Unknown source engine: {body.source_engine}"
        ) from None

    target = None
    if body.target_engine:
        try:
            target = AgentEngineType(body.target_engine)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Unknown target engine: {body.target_engine}"
            ) from None

    try:
        task_type = TaskType(body.task_type)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Unknown task type: {body.task_type}"
        ) from None

    req = HandoffRequest(
        task=body.task,
        task_id=body.task_id,
        source_engine=source,
        reason=body.reason,
        target_engine=target,
        task_type=task_type,
        budget=body.budget,
        timeout_seconds=body.timeout_seconds,
        extract_insights=body.extract_insights,
        artifacts=body.artifacts,
    )
    result = await c.handoff_task.handoff(req)
    return HandoffResponseSchema.from_result(result)


# ---------- Insights ----------


@router.post("/insights/extract", response_model=InsightListResponse)
async def extract_insights(body: InsightExtractRequest, request: Request) -> InsightListResponse:
    """Extract insights from agent output."""
    c = _container(request)

    try:
        engine = AgentEngineType(body.engine)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown engine: {body.engine}") from None

    insights = await c.extract_insights.extract_and_store(
        task_id=body.task_id,
        engine=engine,
        output=body.output,
    )
    return InsightListResponse(
        insights=[InsightResponse.from_insight(i) for i in insights],
        count=len(insights),
    )

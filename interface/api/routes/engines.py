"""Engine CRUD + execution endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from interface.api.schemas import (
    EngineInfoResponse,
    EngineListResponse,
    EngineRunRequest,
    EngineRunResponse,
)

router = APIRouter(prefix="/api/engines", tags=["engines"])


def _container(request: Request):  # noqa: ANN202
    return request.app.state.container


@router.get("", response_model=EngineListResponse)
async def list_engines(request: Request) -> EngineListResponse:
    c = _container(request)
    statuses = await c.route_to_engine.list_engines()
    items = [EngineInfoResponse.from_status(s) for s in statuses]
    return EngineListResponse(engines=items, count=len(items))


@router.get("/{engine_type}", response_model=EngineInfoResponse)
async def get_engine(engine_type: str, request: Request) -> EngineInfoResponse:
    c = _container(request)
    try:
        et = AgentEngineType(engine_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown engine: {engine_type}") from exc
    status = await c.route_to_engine.get_engine(et)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Engine {engine_type} not registered")
    return EngineInfoResponse.from_status(status)


@router.post("/run", response_model=EngineRunResponse)
async def run_engine(body: EngineRunRequest, request: Request) -> EngineRunResponse:
    c = _container(request)

    # Parse optional engine override
    preferred: AgentEngineType | None = None
    if body.engine is not None:
        try:
            preferred = AgentEngineType(body.engine)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Unknown engine: {body.engine}") from exc

    # Parse task type
    try:
        task_type = TaskType(body.task_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown task_type: {body.task_type}") from exc

    result = await c.route_to_engine.execute(
        task=body.task,
        task_type=task_type,
        budget=body.budget,
        preferred_engine=preferred,
        model=body.model,
        timeout_seconds=body.timeout_seconds,
        context=body.context,
    )
    return EngineRunResponse.from_result(result)

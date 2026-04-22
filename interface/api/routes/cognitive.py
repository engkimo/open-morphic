"""UCL / Cognitive API routes — shared task state, affinity, handoff, insights."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from domain.services.agent_affinity import AgentAffinityScorer
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from interface.api.schemas import (
    AffinityListResponse,
    AffinityScoreResponse,
    ConflictListResponse,
    ConflictPairResponse,
    DetectConflictsRequest,
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


# ---------- Conflicts ----------


@router.post("/conflicts", response_model=ConflictListResponse)
async def detect_conflicts(
    body: DetectConflictsRequest, request: Request
) -> ConflictListResponse:
    """Detect (and optionally resolve) conflicts between stored insights."""
    from domain.ports.insight_extractor import ExtractedInsight
    from domain.services.conflict_resolver import ConflictResolver
    from domain.value_objects.cognitive import CognitiveMemoryType
    from domain.value_objects.status import MemoryType

    c = _container(request)

    type_map = {
        MemoryType.L2_SEMANTIC: CognitiveMemoryType.EPISODIC,
        MemoryType.L3_FACTS: CognitiveMemoryType.SEMANTIC,
        MemoryType.L1_ACTIVE: CognitiveMemoryType.WORKING,
    }
    memories: list = []
    for mt in (MemoryType.L2_SEMANTIC, MemoryType.L3_FACTS, MemoryType.L1_ACTIVE):
        memories.extend(await c.memory_repo.list_by_type(mt, limit=body.limit))

    insights: list[ExtractedInsight] = []
    for m in memories:
        engine_str = m.metadata.get("source_engine", "ollama")
        try:
            engine = AgentEngineType(engine_str)
        except ValueError:
            engine = AgentEngineType.OLLAMA
        insights.append(
            ExtractedInsight(
                content=m.content,
                memory_type=type_map.get(m.memory_type, CognitiveMemoryType.EPISODIC),
                confidence=m.importance_score,
                source_engine=engine,
                tags=m.metadata.get("tags", []),
            )
        )

    def _pair_response(cp) -> ConflictPairResponse:  # type: ignore[no-untyped-def]
        return ConflictPairResponse(
            insight_a=InsightResponse.from_insight(cp.insight_a),
            insight_b=InsightResponse.from_insight(cp.insight_b),
            overlap_score=cp.overlap_score,
            winner="a" if cp.resolved_winner is cp.insight_a else "b",
        )

    if body.resolve:
        survivors, conflicts = ConflictResolver.resolve_all(insights)
        return ConflictListResponse(
            conflicts=[_pair_response(cp) for cp in conflicts],
            count=len(conflicts),
            insights_analyzed=len(insights),
            survivors=len(survivors),
        )

    conflicts = ConflictResolver.detect_conflicts(insights)
    return ConflictListResponse(
        conflicts=[_pair_response(cp) for cp in conflicts],
        count=len(conflicts),
        insights_analyzed=len(insights),
    )

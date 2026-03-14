"""API request/response schemas — separate from domain entities.

Plain strings for enums to avoid Pydantic strict-mode issues in JSON.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from domain.entities.cost import CostRecord
from domain.entities.task import SubTask, TaskEntity
from domain.entities.tool_candidate import ToolCandidate

if TYPE_CHECKING:
    from application.use_cases.handoff_task import HandoffResult
    from application.use_cases.route_to_engine import EngineStatus
    from domain.entities.cognitive import AgentAffinityScore, SharedTaskState
    from domain.entities.plan import ExecutionPlan, PlanStep
    from domain.ports.agent_engine import AgentEngineResult
    from domain.ports.insight_extractor import ExtractedInsight


# ── Task schemas ──


class CreateTaskRequest(BaseModel):
    goal: str = Field(min_length=1, examples=["Implement a Fibonacci function in Python"])


class SubTaskResponse(BaseModel):
    id: str
    description: str
    status: str
    dependencies: list[str]
    result: str | None = None
    error: str | None = None
    code: str | None = None
    execution_output: str | None = None
    model_used: str | None = None
    cost_usd: float = 0.0

    @classmethod
    def from_subtask(cls, st: SubTask) -> SubTaskResponse:
        return cls(
            id=st.id,
            description=st.description,
            status=st.status.value,
            dependencies=st.dependencies,
            result=st.result,
            error=st.error,
            code=st.code,
            execution_output=st.execution_output,
            model_used=st.model_used,
            cost_usd=st.cost_usd,
        )


class TaskResponse(BaseModel):
    id: str
    goal: str
    status: str
    subtasks: list[SubTaskResponse]
    total_cost_usd: float
    created_at: datetime
    is_complete: bool
    success_rate: float

    @classmethod
    def from_task(cls, task: TaskEntity) -> TaskResponse:
        return cls(
            id=task.id,
            goal=task.goal,
            status=task.status.value,
            subtasks=[SubTaskResponse.from_subtask(s) for s in task.subtasks],
            total_cost_usd=task.total_cost_usd,
            created_at=task.created_at,
            is_complete=task.is_complete,
            success_rate=task.success_rate,
        )


class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
    count: int


# ── Cost schemas ──


class CostSummaryResponse(BaseModel):
    daily_total_usd: float
    monthly_total_usd: float
    local_usage_rate: float
    monthly_budget_usd: float
    budget_remaining_usd: float


class CostLogEntry(BaseModel):
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    is_local: bool
    timestamp: datetime

    @classmethod
    def from_record(cls, r: CostRecord) -> CostLogEntry:
        return cls(
            model=r.model,
            prompt_tokens=r.prompt_tokens,
            completion_tokens=r.completion_tokens,
            cost_usd=r.cost_usd,
            is_local=r.is_local,
            timestamp=r.timestamp,
        )


class CostLogResponse(BaseModel):
    logs: list[CostLogEntry]
    count: int


# ── Model schemas ──


class ModelInfo(BaseModel):
    name: str
    available: bool


class ModelStatusResponse(BaseModel):
    ollama_running: bool
    default_model: str
    models: list[ModelInfo]


class OllamaModelDetailResponse(BaseModel):
    name: str
    details: dict


class OllamaPullRequest(BaseModel):
    name: str = Field(min_length=1, examples=["qwen3:8b"])


class OllamaSwitchRequest(BaseModel):
    name: str = Field(min_length=1, examples=["qwen3:8b"])


# ── Plan schemas ──


class CreatePlanRequest(BaseModel):
    goal: str = Field(min_length=1, examples=["Build a REST API with authentication"])
    model: str = Field(default="ollama/qwen3:8b", examples=["ollama/qwen3:8b"])


class PlanStepResponse(BaseModel):
    subtask_description: str
    proposed_model: str
    estimated_cost_usd: float
    estimated_tokens: int
    risk_note: str = ""

    @classmethod
    def from_step(cls, step: PlanStep) -> PlanStepResponse:
        return cls(
            subtask_description=step.subtask_description,
            proposed_model=step.proposed_model,
            estimated_cost_usd=step.estimated_cost_usd,
            estimated_tokens=step.estimated_tokens,
            risk_note=step.risk_note,
        )


class ExecutionPlanResponse(BaseModel):
    id: str
    goal: str
    steps: list[PlanStepResponse]
    total_estimated_cost_usd: float
    status: str
    task_id: str | None = None
    created_at: datetime

    @classmethod
    def from_plan(cls, plan: ExecutionPlan) -> ExecutionPlanResponse:
        return cls(
            id=plan.id,
            goal=plan.goal,
            steps=[PlanStepResponse.from_step(s) for s in plan.steps],
            total_estimated_cost_usd=plan.total_estimated_cost_usd,
            status=plan.status.value,
            task_id=plan.task_id,
            created_at=plan.created_at,
        )


class PlanListResponse(BaseModel):
    plans: list[ExecutionPlanResponse]
    count: int


# ── Memory schemas ──


class MemorySearchResponse(BaseModel):
    query: str
    results: list[str]
    count: int


class ContextExportResponse(BaseModel):
    platform: str
    content: str
    token_estimate: int


# ── Engine schemas ──


class EngineRunRequest(BaseModel):
    task: str = Field(min_length=1, examples=["Implement a Fibonacci function in Python"])
    engine: str | None = Field(default=None, examples=["ollama", "claude_code"])
    task_type: str = Field(default="simple_qa", examples=["simple_qa", "complex_reasoning"])
    budget: float = Field(default=1.0, ge=0.0)
    model: str | None = None
    timeout_seconds: float = Field(default=300.0, gt=0.0)
    context: str | None = Field(default=None, description="Optional context to prepend to the task")


class EngineInfoResponse(BaseModel):
    engine_type: str
    available: bool
    max_context_tokens: int
    supports_sandbox: bool
    supports_parallel: bool
    supports_mcp: bool
    cost_per_hour_usd: float

    @classmethod
    def from_status(cls, status: EngineStatus) -> EngineInfoResponse:
        caps = status.capabilities
        return cls(
            engine_type=status.engine_type.value,
            available=status.available,
            max_context_tokens=caps.max_context_tokens,
            supports_sandbox=caps.supports_sandbox,
            supports_parallel=caps.supports_parallel,
            supports_mcp=caps.supports_mcp,
            cost_per_hour_usd=caps.cost_per_hour_usd,
        )


class EngineListResponse(BaseModel):
    engines: list[EngineInfoResponse]
    count: int


class EngineRunResponse(BaseModel):
    engine: str
    success: bool
    output: str
    cost_usd: float
    duration_seconds: float
    model_used: str | None = None
    error: str | None = None

    @classmethod
    def from_result(cls, result: AgentEngineResult) -> EngineRunResponse:
        return cls(
            engine=result.engine.value,
            success=result.success,
            output=result.output,
            cost_usd=result.cost_usd,
            duration_seconds=result.duration_seconds,
            model_used=result.model_used,
            error=result.error,
        )


# ── Marketplace schemas ──


class ToolCandidateResponse(BaseModel):
    name: str
    description: str
    publisher: str
    package_name: str
    transport: str
    install_command: str
    source_url: str
    download_count: int
    safety_tier: str
    safety_score: float

    @classmethod
    def from_candidate(cls, c: ToolCandidate) -> ToolCandidateResponse:
        return cls(
            name=c.name,
            description=c.description,
            publisher=c.publisher,
            package_name=c.package_name,
            transport=c.transport,
            install_command=c.install_command,
            source_url=c.source_url,
            download_count=c.download_count,
            safety_tier=c.safety_tier.name.lower(),
            safety_score=c.safety_score,
        )


class ToolSearchResponse(BaseModel):
    query: str
    candidates: list[ToolCandidateResponse]
    total_count: int
    error: str | None = None


class ToolInstallRequest(BaseModel):
    name: str = Field(min_length=1, examples=["filesystem"])


class ToolInstallResponse(BaseModel):
    tool_name: str
    success: bool
    message: str = ""
    error: str | None = None


class ToolSuggestRequest(BaseModel):
    error_message: str = Field(min_length=1, examples=["FileNotFoundError: config.yaml"])
    task_description: str = ""


class ToolSuggestionResponse(BaseModel):
    suggestions: list[ToolCandidateResponse]
    queries_used: list[str]
    count: int


# ── Evolution schemas ──


class ExecutionStatsResponse(BaseModel):
    total_count: int
    success_count: int
    failure_count: int
    success_rate: float
    avg_cost_usd: float
    avg_duration_seconds: float
    model_distribution: dict[str, int]
    engine_distribution: dict[str, int]


class FailurePatternResponse(BaseModel):
    error_pattern: str
    count: int
    task_types: list[str]
    engines: list[str]


class FailurePatternsListResponse(BaseModel):
    patterns: list[FailurePatternResponse]
    count: int


class ModelPreferenceResponse(BaseModel):
    task_type: str
    model: str
    success_rate: float
    avg_cost_usd: float
    avg_duration_seconds: float
    sample_count: int


class EnginePreferenceResponse(BaseModel):
    task_type: str
    engine: str
    success_rate: float
    avg_cost_usd: float
    avg_duration_seconds: float
    sample_count: int


class PreferencesResponse(BaseModel):
    model_preferences: list[ModelPreferenceResponse]
    engine_preferences: list[EnginePreferenceResponse]


class StrategyUpdateResponse(BaseModel):
    model_preferences_updated: int
    engine_preferences_updated: int
    recovery_rules_added: int
    details: list[str]


class EvolutionReportResponse(BaseModel):
    level: str
    strategy_update: StrategyUpdateResponse | None
    tool_gaps_found: int
    tools_suggested: list[str]
    summary: str
    created_at: datetime


# ---------- UCL / Cognitive ----------


class DecisionResponse(BaseModel):
    id: str
    description: str
    rationale: str
    agent_engine: str
    confidence: float
    timestamp: datetime


class AgentActionResponse(BaseModel):
    id: str
    agent_engine: str
    action_type: str
    summary: str
    cost_usd: float
    duration_seconds: float
    timestamp: datetime


class SharedTaskStateResponse(BaseModel):
    task_id: str
    decisions: list[DecisionResponse]
    artifacts: dict[str, str]
    blockers: list[str]
    agent_history: list[AgentActionResponse]
    last_agent: str | None
    total_cost_usd: float
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_state(cls, s: SharedTaskState) -> SharedTaskStateResponse:
        return cls(
            task_id=s.task_id,
            decisions=[
                DecisionResponse(
                    id=d.id,
                    description=d.description,
                    rationale=d.rationale,
                    agent_engine=d.agent_engine.value,
                    confidence=d.confidence,
                    timestamp=d.timestamp,
                )
                for d in s.decisions
            ],
            artifacts=dict(s.artifacts),
            blockers=list(s.blockers),
            agent_history=[
                AgentActionResponse(
                    id=a.id,
                    agent_engine=a.agent_engine.value,
                    action_type=a.action_type,
                    summary=a.summary,
                    cost_usd=a.cost_usd,
                    duration_seconds=a.duration_seconds,
                    timestamp=a.timestamp,
                )
                for a in s.agent_history
            ],
            last_agent=s.last_agent.value if s.last_agent else None,
            total_cost_usd=s.total_cost_usd,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )


class SharedTaskStateListResponse(BaseModel):
    states: list[SharedTaskStateResponse]
    count: int


class AffinityScoreResponse(BaseModel):
    engine: str
    topic: str
    familiarity: float
    recency: float
    success_rate: float
    cost_efficiency: float
    sample_count: int
    score: float
    last_used: datetime | None

    @classmethod
    def from_affinity(cls, a: AgentAffinityScore, score: float) -> AffinityScoreResponse:
        return cls(
            engine=a.engine.value,
            topic=a.topic,
            familiarity=a.familiarity,
            recency=a.recency,
            success_rate=a.success_rate,
            cost_efficiency=a.cost_efficiency,
            sample_count=a.sample_count,
            score=score,
            last_used=a.last_used,
        )


class AffinityListResponse(BaseModel):
    scores: list[AffinityScoreResponse]
    count: int


class HandoffRequestSchema(BaseModel):
    task: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    source_engine: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    target_engine: str | None = None
    task_type: str = "complex_reasoning"
    budget: float = Field(default=1.0, ge=0.0)
    timeout_seconds: float = Field(default=300.0, ge=1.0)
    extract_insights: bool = False
    artifacts: dict[str, str] = Field(default_factory=dict)


class HandoffResponseSchema(BaseModel):
    success: bool
    source_engine: str
    target_engine: str
    output: str | None
    error: str | None
    state: SharedTaskStateResponse | None

    @classmethod
    def from_result(cls, r: HandoffResult) -> HandoffResponseSchema:
        return cls(
            success=r.success,
            source_engine=r.source_engine.value,
            target_engine=r.target_engine.value,
            output=r.engine_result.output if r.engine_result else None,
            error=r.error,
            state=SharedTaskStateResponse.from_state(r.state) if r.state else None,
        )


class InsightResponse(BaseModel):
    content: str
    memory_type: str
    confidence: float
    source_engine: str
    tags: list[str]

    @classmethod
    def from_insight(cls, i: ExtractedInsight) -> InsightResponse:
        return cls(
            content=i.content,
            memory_type=i.memory_type.value,
            confidence=i.confidence,
            source_engine=i.source_engine.value,
            tags=list(i.tags),
        )


class InsightListResponse(BaseModel):
    insights: list[InsightResponse]
    count: int


class InsightExtractRequest(BaseModel):
    task_id: str = Field(min_length=1)
    engine: str = Field(min_length=1)
    output: str = Field(min_length=1)


# ---------- Benchmarks (Sprint 7.6) ----------


class AdapterScoreResponse(BaseModel):
    engine: str
    decisions_injected: int
    decisions_found: int
    artifacts_injected: int
    artifacts_found: int
    blockers_injected: int
    blockers_found: int
    context_length: int
    score: float


class ContinuityResultResponse(BaseModel):
    overall_score: float
    adapter_scores: list[AdapterScoreResponse]


class DedupScoreResponse(BaseModel):
    scenario: str
    engine_a: str
    engine_b: str
    raw_count_a: int
    raw_count_b: int
    total_raw: int
    deduped_count: int
    dedup_rate: float


class DedupResultResponse(BaseModel):
    overall_accuracy: float
    scores: list[DedupScoreResponse]


class BenchmarkResultResponse(BaseModel):
    overall_score: float
    context_continuity: ContinuityResultResponse | None = None
    dedup_accuracy: DedupResultResponse | None = None
    errors: list[str] = Field(default_factory=list)
    timestamp: str

    @classmethod
    def from_result(cls, r: object) -> BenchmarkResultResponse:
        from benchmarks.runner import BenchmarkSuiteResult

        assert isinstance(r, BenchmarkSuiteResult)
        cc = None
        if r.context_continuity:
            cc = ContinuityResultResponse(
                overall_score=round(r.context_continuity.overall_score, 4),
                adapter_scores=[
                    AdapterScoreResponse(
                        engine=s.engine,
                        decisions_injected=s.decisions_injected,
                        decisions_found=s.decisions_found,
                        artifacts_injected=s.artifacts_injected,
                        artifacts_found=s.artifacts_found,
                        blockers_injected=s.blockers_injected,
                        blockers_found=s.blockers_found,
                        context_length=s.context_length,
                        score=round(s.score, 4),
                    )
                    for s in r.context_continuity.adapter_scores
                ],
            )
        dd = None
        if r.dedup_accuracy:
            dd = DedupResultResponse(
                overall_accuracy=round(r.dedup_accuracy.overall_accuracy, 4),
                scores=[
                    DedupScoreResponse(
                        scenario=s.scenario,
                        engine_a=s.engine_a,
                        engine_b=s.engine_b,
                        raw_count_a=s.raw_count_a,
                        raw_count_b=s.raw_count_b,
                        total_raw=s.total_raw,
                        deduped_count=s.deduped_count,
                        dedup_rate=round(s.dedup_rate, 4),
                    )
                    for s in r.dedup_accuracy.scores
                ],
            )
        return cls(
            overall_score=round(r.overall_score, 4),
            context_continuity=cc,
            dedup_accuracy=dd,
            errors=list(r.errors),
            timestamp=r.timestamp,
        )

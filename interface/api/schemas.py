"""API request/response schemas — separate from domain entities.

Plain strings for enums to avoid Pydantic strict-mode issues in JSON.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from domain.entities.cost import CostRecord
from domain.entities.task import SubTask, TaskEntity

if TYPE_CHECKING:
    from application.use_cases.route_to_engine import EngineStatus
    from domain.entities.plan import ExecutionPlan, PlanStep
    from domain.ports.agent_engine import AgentEngineResult


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

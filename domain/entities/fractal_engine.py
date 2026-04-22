"""Fractal Engine entities — core domain model for recursive execution.

Sprint 15.1: Every execution node is an engine instance. Expanding any node
reveals the same Planner → Plan Evaluator → Agent → Result Evaluator loop.
Recursion continues until atomic tool calls are reached.

Key entities:
  PlanNode — a step in an execution plan (may be expanded into a sub-plan).
  CandidateNode — a generated candidate with iceberg state tracking.
  ExecutionPlan — collection of nodes with candidate space management.
  PlanEvaluation — Gate ① result (Multi-LLM plan evaluation).
  ResultEvaluation — Gate ② result (post-execution evaluation).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects.fractal_engine import (
    NodeState,
    PlanEvalDecision,
    ResultEvalDecision,
)
from domain.value_objects.output_requirement import OutputRequirement
from domain.value_objects.status import PlanStatus, SubTaskStatus


class PlanNode(BaseModel):
    """A node in a fractal execution plan.

    Each node can be terminal (atomic tool call) or expandable
    (spawns a child engine at nesting_level + 1).
    """

    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = Field(min_length=1)
    nesting_level: int = Field(default=0, ge=0)
    status: SubTaskStatus = SubTaskStatus.PENDING
    parent_node_id: str | None = None
    is_terminal: bool = False
    result: str | None = None
    error: str | None = None
    model_used: str | None = None
    cost_usd: float = Field(default=0.0, ge=0.0)
    input_artifacts: dict[str, str] = Field(default_factory=dict)
    output_artifacts: dict[str, str] = Field(default_factory=dict)
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=3, ge=0)
    spawned_by_reflection: bool = False
    output_requirement: OutputRequirement | None = None

    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries


class CandidateNode(BaseModel):
    """A candidate node in the iceberg candidate space.

    Three invisible states (below the surface):
      PRUNED — Gate ① removed before execution.
      FAILED — Gate ② declared failure after execution.
      CONDITIONAL — held until a runtime condition fires.
    One visible state (above the surface):
      VISIBLE — selected for execution.
    """

    model_config = ConfigDict(strict=True, validate_assignment=True)

    node: PlanNode
    state: NodeState = NodeState.VISIBLE
    prune_reason: str | None = None
    failure_reason: str | None = None
    activation_condition: str | None = None
    score: float = Field(default=0.0, ge=0.0, le=1.0)


class ExecutionPlan(BaseModel):
    """A fractal execution plan with candidate space.

    The visible_nodes list is the surface of the iceberg — the active
    execution sequence. The candidate_space holds all generated-but-not-
    adopted nodes (pruned, failed, conditional).
    """

    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str = Field(min_length=1)
    nesting_level: int = Field(default=0, ge=0)
    parent_plan_id: str | None = None
    parent_node_id: str | None = None
    visible_nodes: list[PlanNode] = Field(default_factory=list)
    candidate_space: list[CandidateNode] = Field(default_factory=list)
    status: PlanStatus = PlanStatus.PROPOSED
    reflection_rounds: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def visible_count(self) -> int:
        return len(self.visible_nodes)

    @property
    def pruned_count(self) -> int:
        return sum(1 for c in self.candidate_space if c.state == NodeState.PRUNED)

    @property
    def conditional_count(self) -> int:
        return sum(1 for c in self.candidate_space if c.state == NodeState.CONDITIONAL)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.candidate_space if c.state == NodeState.FAILED)

    def get_conditional_nodes(self) -> list[CandidateNode]:
        """Return all conditionally held nodes."""
        return [c for c in self.candidate_space if c.state == NodeState.CONDITIONAL]

    def get_ready_nodes(self) -> list[PlanNode]:
        """Return visible nodes that are PENDING (ready to execute)."""
        return [n for n in self.visible_nodes if n.status == SubTaskStatus.PENDING]


class PlanEvaluation(BaseModel):
    """Gate ① — Multi-LLM plan evaluation result.

    Multiple evaluators (completeness, feasibility, safety) independently
    score the plan. The overall_score determines approval/rejection.
    """

    model_config = ConfigDict(strict=True, validate_assignment=True)

    plan_id: str = Field(min_length=1)
    evaluator_model: str = Field(default="")
    completeness: float = Field(default=0.0, ge=0.0, le=1.0)
    feasibility: float = Field(default=0.0, ge=0.0, le=1.0)
    safety: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0)
    decision: PlanEvalDecision = PlanEvalDecision.REJECTED
    feedback: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class ResultEvaluation(BaseModel):
    """Gate ② — post-execution result evaluation.

    Evaluates node execution output against goal alignment, accuracy,
    and validity. Decides: OK (advance), RETRY (re-execute), REPLAN
    (return to Planner for revision).
    """

    model_config = ConfigDict(strict=True, validate_assignment=True)

    node_id: str = Field(min_length=1)
    decision: ResultEvalDecision = ResultEvalDecision.OK
    accuracy: float = Field(default=0.0, ge=0.0, le=1.0)
    validity: float = Field(default=0.0, ge=0.0, le=1.0)
    goal_alignment: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0)
    feedback: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)

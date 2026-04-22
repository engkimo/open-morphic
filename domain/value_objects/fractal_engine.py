"""Fractal Engine value objects — node states and evaluation decisions.

Sprint 15.1: Domain model for the fractal recursive engine architecture.
Every execution node is an engine instance with dual evaluation gates.
"""

from enum import Enum


class NodeState(str, Enum):
    """State of a candidate node in the iceberg candidate space.

    VISIBLE — selected for execution (surface of the iceberg).
    PRUNED — removed by Gate ① (Plan Evaluator) before execution.
    FAILED — attempted execution, declared failure by Gate ②.
    CONDITIONAL — held in reserve until a runtime condition fires.
    """

    VISIBLE = "visible"
    PRUNED = "pruned"
    FAILED = "failed"
    CONDITIONAL = "conditional"


class PlanEvalDecision(str, Enum):
    """Gate ① decision — Multi-LLM Plan Evaluator outcome."""

    APPROVED = "approved"
    REJECTED = "rejected"


class ResultEvalDecision(str, Enum):
    """Gate ② decision — Result Evaluator outcome after execution.

    OK — advance to next node.
    RETRY — re-execute the same node.
    REPLAN — return to Planner for plan revision.
    """

    OK = "ok"
    RETRY = "retry"
    REPLAN = "replan"


class EvalAxis(str, Enum):
    """Evaluation axes for Gate ① Plan Evaluator."""

    COMPLETENESS = "completeness"
    FEASIBILITY = "feasibility"
    SAFETY = "safety"

"""AgentState — LangGraph state definition for task execution."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class AgentState(TypedDict):
    """Execution state for the LangGraph DAG.

    The TaskEntity is held by reference on the engine instance
    to avoid Pydantic strict-mode serialization issues.
    """

    ready_ids: list[str]
    history: Annotated[list[dict], operator.add]
    status: str  # "running" | "done" | "failed"
    cost_so_far: float

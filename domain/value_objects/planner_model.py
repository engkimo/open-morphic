"""PlannerModel — selects the LLM used by ``LLMPlanner`` per goal.

Routed by ``PlannerModelRouter`` based on a goal classifier's output.
``to_gateway_id`` resolves the enum to the concrete model id passed to
``LLMGateway.complete`` (which in turn flows through LiteLLM to Anthropic).
"""

from __future__ import annotations

from enum import Enum


class PlannerModel(str, Enum):
    """Two candidate planner models."""

    SONNET = "sonnet"
    HAIKU = "haiku"

    def to_gateway_id(self) -> str:
        """Resolve to the concrete LLMGateway model id."""
        if self is PlannerModel.SONNET:
            return "claude-sonnet-4-6"
        return "claude-haiku-4-5-20251001"

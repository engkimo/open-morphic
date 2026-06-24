"""Council runtime entities for Morphic Chat CLI deliberation."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CouncilRole(str, Enum):
    """Deliberation responsibilities independent from execution engines."""

    PLANNER = "planner"
    ARCHITECT = "architect"
    IMPLEMENTER = "implementer"
    CRITIC = "critic"
    TESTER = "tester"
    LEADER = "leader"
    REFLECTOR = "reflector"


class CouncilTurn(BaseModel):
    """One role contribution produced by an engine."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    role: CouncilRole
    engine_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    cost_usd: float = Field(default=0.0, ge=0.0)
    latency_ms: int = Field(default=0, ge=0)


class CouncilDecision(BaseModel):
    """Leader decision based on role output and evidence."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    leader_engine_id: str = Field(min_length=1)
    selected_role: CouncilRole
    selected_content: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    rejected_options: list[str] = Field(default_factory=list)

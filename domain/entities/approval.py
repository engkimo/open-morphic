"""Approval entities for user-supervised chat execution."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects import RiskLevel


class ApprovalStatus(str, Enum):
    """Lifecycle state for an approval request."""

    PENDING = "pending"
    RESOLVED = "resolved"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalDecisionStatus(str, Enum):
    """Decision made for an approval request."""

    APPROVED = "approved"
    DENIED = "denied"
    CANCELLED = "cancelled"


class ApprovalRequest(BaseModel):
    """A risk-bearing action that needs user approval."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1)
    session_id: str = Field(min_length=1)
    action_summary: str = Field(min_length=1)
    risk_level: RiskLevel
    reason: str = Field(min_length=1)
    options: list[str] = Field(default_factory=lambda: ["approve", "deny"])
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    @property
    def requires_user_decision(self) -> bool:
        return self.status is ApprovalStatus.PENDING


class ApprovalDecision(BaseModel):
    """Resolved user decision for a pending approval request."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    request_id: str = Field(min_length=1)
    status: ApprovalDecisionStatus
    decided_by: str = Field(min_length=1)
    rationale: str | None = None
    decided_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

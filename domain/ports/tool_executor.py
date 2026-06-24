"""Port for LAEE-compatible chat tool execution."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects import RiskLevel


class ToolExecutionRequest(BaseModel):
    """Normalized tool execution request recorded by chat sessions."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1)
    session_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.SAFE
    requires_approval: bool = False
    approval_id: str | None = None
    requested_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class ToolExecutionResult(BaseModel):
    """Normalized result from an executed tool action."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    request_id: str = Field(min_length=1)
    success: bool
    stdout_summary: str = ""
    stderr_summary: str = ""
    exit_code: int | None = None
    artifacts: list[str] = Field(default_factory=list)
    completed_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class ToolExecutorPort(ABC):
    """Executes normalized chat tools through LAEE-compatible infrastructure."""

    @abstractmethod
    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult: ...

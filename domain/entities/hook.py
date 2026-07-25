"""Hook definitions for Morphic Chat CLI harness events."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class HookType(str, Enum):
    """Supported hook trigger points."""

    PRE_TOOL = "pre_tool"
    POST_TOOL = "post_tool"
    PRE_EDIT = "pre_edit"
    POST_EDIT = "post_edit"
    PRE_SHELL = "pre_shell"
    POST_SHELL = "post_shell"
    PRE_COMMIT = "pre_commit"
    SESSION_END = "session_end"


class HookDefinition(BaseModel):
    """Validated hook definition discovered from workspace metadata."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    name: str = Field(min_length=1)
    hook_type: HookType
    command: str = Field(min_length=1)
    enabled: bool = True
    source_path: str = Field(min_length=1)


class HookDiagnostic(BaseModel):
    """Validation result for one hook source."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    name: str = Field(min_length=1)
    status: str = Field(min_length=1)
    message: str = Field(min_length=1)
    source_path: str | None = Field(default=None, min_length=1)
    duration_ms: float = Field(default=0.0, ge=0.0)


class HookExecutionRequest(BaseModel):
    """Normalized request to execute one validated hook command."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1)
    session_id: str = Field(min_length=1)
    hook_name: str = Field(min_length=1)
    hook_type: HookType
    command: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class HookExecutionResult(BaseModel):
    """Normalized result from a hook executor implementation."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    request_id: str = Field(min_length=1)
    success: bool
    stdout_summary: str = ""
    stderr_summary: str = ""
    exit_code: int | None = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

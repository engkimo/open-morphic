"""Hook definitions for Morphic Chat CLI harness events."""

from __future__ import annotations

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

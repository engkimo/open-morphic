"""Execution entities — Action and Observation for LAEE and task execution."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects import RiskLevel
from domain.value_objects.status import ObservationStatus


class Action(BaseModel):
    """An action to execute on the local machine or via LLM."""

    model_config = ConfigDict(strict=True)

    tool: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    risk: RiskLevel = RiskLevel.SAFE
    reversible: bool = False
    undo_hint: str | None = None


class Observation(BaseModel):
    """Result of executing an action."""

    model_config = ConfigDict(strict=True)

    status: ObservationStatus
    result: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class UndoAction(BaseModel):
    """Stored undo information for reversible actions."""

    model_config = ConfigDict(strict=True)

    original_tool: str = Field(min_length=1)
    original_args: dict[str, Any]
    undo_tool: str = Field(min_length=1)
    undo_args: dict[str, Any]
    created_at: datetime = Field(default_factory=datetime.now)

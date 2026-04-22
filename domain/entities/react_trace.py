"""ReAct trace entities — records of Think-Act-Observe iterations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolCallRecord(BaseModel):
    """A single tool call requested by the LLM."""

    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ReactStep(BaseModel):
    """One iteration of Think → Act → Observe."""

    model_config = ConfigDict(strict=True, validate_assignment=True)

    step_number: int = Field(ge=0)
    thought: str = ""
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    error: str | None = None


class ReactTrace(BaseModel):
    """Complete trace of a ReAct execution loop."""

    model_config = ConfigDict(strict=True, validate_assignment=True)

    steps: list[ReactStep] = Field(default_factory=list)
    final_answer: str | None = None
    terminated_reason: (
        Literal["final_answer", "max_iterations", "repetitive_tool_loop", "error"]
        | None
    ) = None

    @property
    def total_iterations(self) -> int:
        return len(self.steps)

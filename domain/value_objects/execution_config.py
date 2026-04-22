"""ExecutionConfig — frozen value object for complexity-aware LLM execution parameters."""

from __future__ import annotations

from dataclasses import dataclass

from domain.value_objects.task_complexity import TaskComplexity


@dataclass(frozen=True)
class ExecutionConfig:
    """Immutable execution parameters derived from task complexity."""

    system_prompt: str
    user_prompt: str
    temperature: float
    max_tokens: int
    complexity: TaskComplexity

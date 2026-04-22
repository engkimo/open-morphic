"""ExecutionPromptBuilder — complexity-aware prompt and parameter selection.

Pure domain service: no I/O, no framework dependencies.
Builds ExecutionConfig from subtask description + complexity + goal.
"""

from __future__ import annotations

from domain.value_objects.execution_config import ExecutionConfig
from domain.value_objects.task_complexity import TaskComplexity

# Format instructions per complexity level
_FORMAT_INSTRUCTIONS: dict[TaskComplexity, str] = {
    TaskComplexity.SIMPLE: (
        "Respond with ONLY the direct answer. No explanation, no reasoning, no preamble."
    ),
    TaskComplexity.MEDIUM: "Provide a concise solution with brief context.",
    TaskComplexity.COMPLEX: "Provide a detailed, thorough response with reasoning.",
}

# LLM parameters per complexity level
_TEMPERATURE: dict[TaskComplexity, float] = {
    TaskComplexity.SIMPLE: 0.15,
    TaskComplexity.MEDIUM: 0.4,
    TaskComplexity.COMPLEX: 0.7,
}

_MAX_TOKENS: dict[TaskComplexity, int] = {
    TaskComplexity.SIMPLE: 512,
    TaskComplexity.MEDIUM: 2048,
    TaskComplexity.COMPLEX: 4096,
}


class ExecutionPromptBuilder:
    """Build ExecutionConfig from task context and complexity.

    Accepts a stable_prefix for KV-cache compliance: the prefix is always
    identical across calls, with format instructions appended after.
    """

    def __init__(self, stable_prefix: str) -> None:
        self._stable_prefix = stable_prefix

    def build(
        self,
        description: str,
        complexity: TaskComplexity,
        goal: str,
    ) -> ExecutionConfig:
        """Build execution configuration for a subtask.

        Args:
            description: The subtask description (becomes user prompt).
            complexity: Classified complexity level.
            goal: The parent task goal (injected into system context).

        Returns:
            Frozen ExecutionConfig with prompts and LLM parameters.
        """
        format_instruction = _FORMAT_INSTRUCTIONS[complexity]
        system_prompt = f"{self._stable_prefix}\n\nGoal: {goal}\n\nFormat: {format_instruction}"

        return ExecutionConfig(
            system_prompt=system_prompt,
            user_prompt=description,
            temperature=_TEMPERATURE[complexity],
            max_tokens=_MAX_TOKENS[complexity],
            complexity=complexity,
        )

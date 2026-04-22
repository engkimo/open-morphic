"""Tests for ExecutionPromptBuilder — complexity-aware prompt generation."""

import pytest

from domain.services.execution_prompt_builder import ExecutionPromptBuilder
from domain.value_objects.execution_config import ExecutionConfig
from domain.value_objects.task_complexity import TaskComplexity

STABLE_PREFIX = "You are Morphic-Agent, a self-evolving AI agent framework."


@pytest.fixture
def builder() -> ExecutionPromptBuilder:
    return ExecutionPromptBuilder(stable_prefix=STABLE_PREFIX)


class TestExecutionPromptBuilder:
    def test_returns_execution_config(self, builder: ExecutionPromptBuilder) -> None:
        config = builder.build("What is 1+1?", TaskComplexity.SIMPLE, "Math quiz")
        assert isinstance(config, ExecutionConfig)

    def test_simple_temperature(self, builder: ExecutionPromptBuilder) -> None:
        config = builder.build("1+1=?", TaskComplexity.SIMPLE, "math")
        assert config.temperature == 0.15

    def test_medium_temperature(self, builder: ExecutionPromptBuilder) -> None:
        config = builder.build("Write a function", TaskComplexity.MEDIUM, "code")
        assert config.temperature == 0.4

    def test_complex_temperature(self, builder: ExecutionPromptBuilder) -> None:
        config = builder.build("Design auth system", TaskComplexity.COMPLEX, "arch")
        assert config.temperature == 0.7

    def test_simple_max_tokens(self, builder: ExecutionPromptBuilder) -> None:
        config = builder.build("1+1=?", TaskComplexity.SIMPLE, "math")
        assert config.max_tokens == 512

    def test_medium_max_tokens(self, builder: ExecutionPromptBuilder) -> None:
        config = builder.build("Write a function", TaskComplexity.MEDIUM, "code")
        assert config.max_tokens == 2048

    def test_complex_max_tokens(self, builder: ExecutionPromptBuilder) -> None:
        config = builder.build("Design system", TaskComplexity.COMPLEX, "arch")
        assert config.max_tokens == 4096

    def test_system_prompt_starts_with_stable_prefix(self, builder: ExecutionPromptBuilder) -> None:
        config = builder.build("task", TaskComplexity.SIMPLE, "goal")
        assert config.system_prompt.startswith(STABLE_PREFIX)

    def test_system_prompt_contains_goal(self, builder: ExecutionPromptBuilder) -> None:
        config = builder.build("task", TaskComplexity.MEDIUM, "Build a REST API")
        assert "Build a REST API" in config.system_prompt

    def test_simple_format_instruction_in_prompt(self, builder: ExecutionPromptBuilder) -> None:
        config = builder.build("1+1", TaskComplexity.SIMPLE, "math")
        assert "ONLY the direct answer" in config.system_prompt

    def test_complex_format_instruction_in_prompt(self, builder: ExecutionPromptBuilder) -> None:
        config = builder.build("design", TaskComplexity.COMPLEX, "arch")
        assert "detailed, thorough" in config.system_prompt

    def test_user_prompt_is_description(self, builder: ExecutionPromptBuilder) -> None:
        config = builder.build("Calculate 2+2", TaskComplexity.SIMPLE, "math")
        assert config.user_prompt == "Calculate 2+2"

    def test_config_is_frozen(self, builder: ExecutionPromptBuilder) -> None:
        config = builder.build("task", TaskComplexity.SIMPLE, "goal")
        with pytest.raises(AttributeError):
            config.temperature = 0.9  # type: ignore[misc]

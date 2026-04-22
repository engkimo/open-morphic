"""Tests for Goal Grounding — Plan A improvements.

Verifies that:
- LLMPlanner system prompt includes entity-preservation rules
- NodeExecutor._build_task includes original goal in task.goal
- TOOL_USAGE_INSTRUCTION includes search-specific guidance
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from domain.entities.fractal_engine import PlanNode
from domain.ports.task_engine import TaskEngine
from infrastructure.fractal.node_executor import NodeExecutor
from infrastructure.task_graph.engine import TOOL_USAGE_INSTRUCTION


class TestPlannerPromptEntityPreservation:
    def test_system_prompt_includes_entity_preservation_rule(self):
        from infrastructure.fractal.llm_planner import _SYSTEM_PROMPT

        assert "MUST preserve the specific entities" in _SYSTEM_PROMPT
        assert "Do NOT abstract them away" in _SYSTEM_PROMPT

    def test_system_prompt_has_good_bad_examples(self):
        from infrastructure.fractal.llm_planner import _SYSTEM_PROMPT

        assert 'BAD:  "Search for information"' in _SYSTEM_PROMPT
        assert "GOOD:" in _SYSTEM_PROMPT

    def test_system_prompt_file_format_rule(self):
        from infrastructure.fractal.llm_planner import _SYSTEM_PROMPT

        assert "file format or tool" in _SYSTEM_PROMPT


class TestNodeExecutorGoalContext:
    @pytest.fixture
    def executor(self) -> NodeExecutor:
        return NodeExecutor(AsyncMock(spec=TaskEngine))

    def test_build_task_includes_original_goal(self, executor):
        node = PlanNode(description="Search for shrine history", is_terminal=True)
        task = executor._build_task(node, "Research Hikawa Shrine history and create slides")
        assert "[Original goal:" in task.goal
        assert "Hikawa Shrine" in task.goal

    def test_build_task_includes_current_step(self, executor):
        node = PlanNode(description="Search for shrine history", is_terminal=True)
        task = executor._build_task(node, "Research Hikawa Shrine")
        assert "Current step:" in task.goal
        assert "Search for shrine history" in task.goal

    def test_build_task_with_artifacts_adds_context(self, executor):
        node = PlanNode(
            description="Generate report",
            is_terminal=True,
            input_artifacts={"data": "Some research data about Hikawa Shrine"},
        )
        task = executor._build_task(node, "Create Hikawa Shrine report")
        subtask = task.subtasks[0]
        assert "Available context:" in subtask.description
        assert "data:" in subtask.description


class TestToolUsageInstruction:
    def test_includes_search_specificity_rule(self):
        assert "SPECIFIC topic/entity" in TOOL_USAGE_INSTRUCTION

    def test_forbids_generic_search_terms(self):
        assert "検索キーワード" in TOOL_USAGE_INSTRUCTION
        assert "search keyword" in TOOL_USAGE_INSTRUCTION

    def test_includes_file_creation_rule(self):
        assert "fs_write" in TOOL_USAGE_INSTRUCTION
        assert "creating a FILE" in TOOL_USAGE_INSTRUCTION

    def test_includes_search_example(self):
        assert "氷川神社" in TOOL_USAGE_INSTRUCTION

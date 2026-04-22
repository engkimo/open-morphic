"""Tests for ToolSelector domain service."""

from domain.services.tool_selector import DEFAULT_TOOLS, TASK_TOOL_PROFILES, ToolSelector
from domain.value_objects.model_tier import TaskType


class TestToolSelector:
    def test_simple_qa(self):
        tools = ToolSelector.select(TaskType.SIMPLE_QA)
        assert "web_search" in tools
        assert "web_fetch" in tools

    def test_code_generation(self):
        tools = ToolSelector.select(TaskType.CODE_GENERATION)
        assert "shell_exec" in tools
        assert "web_search" in tools

    def test_file_operation(self):
        tools = ToolSelector.select(TaskType.FILE_OPERATION)
        assert "fs_read" in tools
        assert "fs_write" in tools
        assert "fs_delete" in tools

    def test_all_task_types_have_profiles(self):
        for task_type in TaskType:
            tools = ToolSelector.select(task_type)
            assert isinstance(tools, list)
            assert len(tools) > 0

    def test_default_tools(self):
        assert "web_search" in DEFAULT_TOOLS
        assert "web_fetch" in DEFAULT_TOOLS
        assert "fs_read" in DEFAULT_TOOLS
        assert "shell_exec" in DEFAULT_TOOLS

    def test_profiles_dict_covers_all_types(self):
        for task_type in TaskType:
            assert task_type in TASK_TOOL_PROFILES

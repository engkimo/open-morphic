"""Tests for Context Engineering — Manus 5 Principles.

CC#1: System prompt first ~128 tokens are always identical (KVCacheOptimizer)
CC#2: Tool definition count does not change during execution (ToolStateMachine)
CC#3: todo.md auto-updated before/after task execution (FileTodoManager)
CC#4: 3 consecutive similar observations serialized with different formats (ObservationDiversifier)
"""

from __future__ import annotations

import json

import pytest

from domain.entities.task import SubTask, TaskEntity
from domain.services.tool_state_machine import ToolDefinition, ToolStateMachine
from domain.value_objects.tool_state import ToolState
from domain.value_objects.status import SubTaskStatus
from infrastructure.context_engineering.file_context import FileContext
from infrastructure.context_engineering.kv_cache_optimizer import KVCacheOptimizer
from infrastructure.context_engineering.observation_diversifier import (
    ObservationDiversifier,
)
from infrastructure.context_engineering.todo_manager import FileTodoManager


# ═══════════════════════════════════════════════════════════════
# CC#2: ToolStateMachine — tool count invariant
# ═══════════════════════════════════════════════════════════════


class TestToolStateMachine:
    """Manus Principle 2: mask tools, never add/remove."""

    @pytest.fixture()
    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(name="shell_exec", description="Execute shell command"),
            ToolDefinition(name="fs_read", description="Read file"),
            ToolDefinition(name="fs_write", description="Write file"),
            ToolDefinition(name="browser_navigate", description="Navigate browser"),
            ToolDefinition(name="browser_click", description="Click element"),
        ]

    @pytest.fixture()
    def sm(self, tools: list[ToolDefinition]) -> ToolStateMachine:
        return ToolStateMachine(tools)

    def test_initial_all_enabled(self, sm: ToolStateMachine) -> None:
        assert sm.total_count == 5
        assert len(sm.get_enabled_tools()) == 5

    def test_mask_reduces_enabled_not_total(self, sm: ToolStateMachine) -> None:
        sm.mask("shell_exec")
        assert sm.total_count == 5  # CC#2: invariant
        assert len(sm.get_enabled_tools()) == 4
        assert sm.get_state("shell_exec") == ToolState.MASKED

    def test_unmask_restores(self, sm: ToolStateMachine) -> None:
        sm.mask("fs_read")
        sm.unmask("fs_read")
        assert sm.get_state("fs_read") == ToolState.ENABLED
        assert len(sm.get_enabled_tools()) == 5

    def test_total_count_invariant_after_many_operations(
        self, sm: ToolStateMachine
    ) -> None:
        """CC#2: total_count never changes regardless of mask/unmask."""
        sm.mask("shell_exec")
        sm.mask("fs_read")
        sm.mask("fs_write")
        assert sm.total_count == 5
        sm.unmask("shell_exec")
        assert sm.total_count == 5
        assert len(sm.get_all_tools()) == 5

    def test_mask_unknown_tool_raises(self, sm: ToolStateMachine) -> None:
        with pytest.raises(KeyError, match="Unknown tool"):
            sm.mask("nonexistent")

    def test_unmask_unknown_tool_raises(self, sm: ToolStateMachine) -> None:
        with pytest.raises(KeyError, match="Unknown tool"):
            sm.unmask("nonexistent")

    def test_mask_by_prefix(self, sm: ToolStateMachine) -> None:
        count = sm.mask_by_prefix("browser_")
        assert count == 2
        assert sm.total_count == 5  # CC#2
        assert len(sm.get_enabled_tools()) == 3

    def test_unmask_by_prefix(self, sm: ToolStateMachine) -> None:
        sm.mask_by_prefix("fs_")
        count = sm.unmask_by_prefix("fs_")
        assert count == 2
        assert len(sm.get_enabled_tools()) == 5

    def test_get_all_tools_returns_all_regardless_of_state(
        self, sm: ToolStateMachine
    ) -> None:
        sm.mask("shell_exec")
        sm.mask("fs_read")
        all_tools = sm.get_all_tools()
        assert len(all_tools) == 5
        names = {t.name for t in all_tools}
        assert "shell_exec" in names
        assert "fs_read" in names


# ═══════════════════════════════════════════════════════════════
# CC#1: KVCacheOptimizer — stable prefix
# ═══════════════════════════════════════════════════════════════


class TestKVCacheOptimizer:
    """Manus Principle 1: KV-cache friendly system prompts."""

    @pytest.fixture()
    def optimizer(self) -> KVCacheOptimizer:
        return KVCacheOptimizer()

    def test_stable_prefix_always_first(self, optimizer: KVCacheOptimizer) -> None:
        """CC#1: prompt always starts with the identical stable prefix."""
        prompt1 = optimizer.build_system_prompt()
        prompt2 = optimizer.build_system_prompt({"goal": "test"})
        prompt3 = optimizer.build_system_prompt({"goal": "different", "step": 5})

        prefix = optimizer.stable_prefix
        assert prompt1.startswith(prefix)
        assert prompt2.startswith(prefix)
        assert prompt3.startswith(prefix)

    def test_prefix_identical_across_calls(self, optimizer: KVCacheOptimizer) -> None:
        """CC#1: first N chars are byte-identical regardless of dynamic context."""
        p1 = optimizer.build_system_prompt()
        p2 = optimizer.build_system_prompt({"x": 1})
        p3 = optimizer.build_system_prompt({"y": 2, "z": 3})

        prefix_len = len(optimizer.stable_prefix)
        assert p1[:prefix_len] == p2[:prefix_len] == p3[:prefix_len]

    def test_no_dynamic_context_returns_prefix_only(
        self, optimizer: KVCacheOptimizer
    ) -> None:
        prompt = optimizer.build_system_prompt()
        assert prompt == optimizer.stable_prefix

    def test_dynamic_context_appended_after_prefix(
        self, optimizer: KVCacheOptimizer
    ) -> None:
        prompt = optimizer.build_system_prompt({"goal": "fibonacci"})
        assert "fibonacci" in prompt
        assert prompt.index("fibonacci") > len(optimizer.stable_prefix)

    def test_deterministic_serialization(self) -> None:
        """JSON sort_keys ensures identical serialization for same data."""
        ctx1 = {"b": 2, "a": 1, "c": 3}
        ctx2 = {"c": 3, "a": 1, "b": 2}
        s1 = KVCacheOptimizer.serialize_context(ctx1)
        s2 = KVCacheOptimizer.serialize_context(ctx2)
        assert s1 == s2
        assert json.loads(s1) == ctx1

    def test_validate_prefix_stability(self, optimizer: KVCacheOptimizer) -> None:
        good = optimizer.build_system_prompt({"x": 1})
        assert optimizer.validate_prefix_stability(good) is True
        assert optimizer.validate_prefix_stability("Wrong prefix") is False

    def test_custom_prefix(self) -> None:
        custom = KVCacheOptimizer(stable_prefix="Custom AI Agent.")
        prompt = custom.build_system_prompt({"goal": "test"})
        assert prompt.startswith("Custom AI Agent.")


# ═══════════════════════════════════════════════════════════════
# CC#4: ObservationDiversifier — template rotation
# ═══════════════════════════════════════════════════════════════


class TestObservationDiversifier:
    """Manus Principle 5: diverse observation formats prevent drift."""

    @pytest.fixture()
    def diversifier(self) -> ObservationDiversifier:
        return ObservationDiversifier()

    def test_consecutive_observations_different_format(
        self, diversifier: ObservationDiversifier
    ) -> None:
        """CC#4: 3 consecutive similar observations → 3 different formats."""
        obs = {"result": "OK", "status": "success"}
        formats = [diversifier.serialize(obs, i) for i in range(3)]
        assert len(set(formats)) == 3  # All different

    def test_four_consecutive_all_different(
        self, diversifier: ObservationDiversifier
    ) -> None:
        """All 4 default templates produce distinct output."""
        obs = {"result": "data", "status": "done"}
        formats = [diversifier.serialize(obs, i) for i in range(4)]
        assert len(set(formats)) == 4

    def test_rotation_wraps_around(self, diversifier: ObservationDiversifier) -> None:
        """After exhausting templates, wraps back to first."""
        obs = {"result": "test", "status": "ok"}
        n = diversifier.template_count
        f0 = diversifier.serialize(obs, 0)
        fn = diversifier.serialize(obs, n)
        assert f0 == fn  # Same template after full rotation

    def test_step_index_in_output(self, diversifier: ObservationDiversifier) -> None:
        """Templates that use {n} include the step index."""
        obs = {"result": "test", "status": "ok"}
        s = diversifier.serialize(obs, 42)
        # At least one template uses {n}, so check step 42 appears somewhere
        # Template index 42 % 4 = 2 → "Completed: test | State: ok" (no {n})
        # Template index 43 % 4 = 3 → "[ok] >> test (step 43)"
        s43 = diversifier.serialize(obs, 43)
        assert "43" in s43

    def test_are_consecutive_diverse(self, diversifier: ObservationDiversifier) -> None:
        obs_list = [{"result": "r", "status": "s"}] * 3
        assert diversifier.are_consecutive_diverse(obs_list, 0) is True

    def test_minimum_two_templates_required(self) -> None:
        with pytest.raises(ValueError, match="At least 2"):
            ObservationDiversifier(templates=["only one"])


# ═══════════════════════════════════════════════════════════════
# CC#3: FileTodoManager — auto-update todo.md
# ═══════════════════════════════════════════════════════════════


class TestTodoManager:
    """Manus Principle 4: todo.md attention steering."""

    @pytest.fixture()
    def todo_path(self, tmp_path):
        return tmp_path / "todo.md"

    @pytest.fixture()
    def manager(self, todo_path) -> FileTodoManager:
        return FileTodoManager(todo_path)

    def test_read_empty_when_no_file(self, manager: FileTodoManager) -> None:
        assert manager.read() == ""

    def test_update_creates_file(
        self, manager: FileTodoManager, todo_path
    ) -> None:
        task = TaskEntity(
            goal="Build fibonacci",
            subtasks=[
                SubTask(description="Write code"),
                SubTask(description="Write tests"),
            ],
        )
        manager.update_from_task(task)
        assert todo_path.exists()
        content = todo_path.read_text()
        assert "Build fibonacci" in content
        assert "[ ] Write code" in content
        assert "[ ] Write tests" in content

    def test_update_reflects_status_changes(
        self, manager: FileTodoManager, todo_path
    ) -> None:
        """CC#3: todo.md updated before/after — status markers change."""
        s1 = SubTask(description="Step A")
        s2 = SubTask(description="Step B")
        task = TaskEntity(goal="Test", subtasks=[s1, s2])

        manager.update_from_task(task)
        content_before = todo_path.read_text()
        assert "[ ] Step A" in content_before

        s1.status = SubTaskStatus.SUCCESS
        s2.status = SubTaskStatus.RUNNING
        manager.update_from_task(task)
        content_after = todo_path.read_text()
        assert "[x] Step A" in content_after
        assert "**[IN PROGRESS]** Step B" in content_after

    def test_progress_percentage(self, manager: FileTodoManager) -> None:
        s1 = SubTask(description="A")
        s2 = SubTask(description="B")
        s1.status = SubTaskStatus.SUCCESS
        task = TaskEntity(goal="Half done", subtasks=[s1, s2])
        content = manager.format_for_context(task)
        assert "50%" in content

    def test_format_for_context_matches_file_content(
        self, manager: FileTodoManager
    ) -> None:
        task = TaskEntity(
            goal="Format test",
            subtasks=[SubTask(description="Only step")],
        )
        manager.update_from_task(task)
        file_content = manager.read()
        ctx_content = manager.format_for_context(task)
        assert file_content == ctx_content

    def test_failed_subtask_rendered(self, manager: FileTodoManager) -> None:
        s1 = SubTask(description="Broken step")
        s1.status = SubTaskStatus.FAILED
        task = TaskEntity(goal="Fail test", subtasks=[s1])
        content = manager.format_for_context(task)
        assert "~~FAILED~~" in content

    def test_nested_directory_created(self, tmp_path) -> None:
        deep_path = tmp_path / "a" / "b" / "todo.md"
        manager = FileTodoManager(deep_path)
        task = TaskEntity(goal="Deep", subtasks=[SubTask(description="Step")])
        manager.update_from_task(task)
        assert deep_path.exists()


# ═══════════════════════════════════════════════════════════════
# Principle 3: FileContext — filesystem as infinite context
# ═══════════════════════════════════════════════════════════════


class TestFileContext:
    """Manus Principle 3: offload content to filesystem."""

    @pytest.fixture()
    def ctx(self, tmp_path) -> FileContext:
        return FileContext(cache_dir=tmp_path / "cache")

    def test_store_and_retrieve(self, ctx: FileContext) -> None:
        content = "Hello, this is a large webpage content..."
        ref = ctx.store(content, label="test_page")
        assert "[Cached:" in ref
        assert "[Label: test_page]" in ref

        # Extract hash from reference
        content_hash = ref.split("[Cached: ")[1].split("]")[0]
        retrieved = ctx.retrieve(content_hash)
        assert retrieved == content

    def test_retrieve_nonexistent_returns_none(self, ctx: FileContext) -> None:
        assert ctx.retrieve("nonexistent_hash") is None

    def test_exists_check(self, ctx: FileContext) -> None:
        content = "Check existence"
        ref = ctx.store(content)
        content_hash = ref.split("[Cached: ")[1].split("]")[0]
        assert ctx.exists(content_hash) is True
        assert ctx.exists("nope") is False

    def test_same_content_same_hash(self, ctx: FileContext) -> None:
        """Deterministic: same content always produces same hash."""
        ref1 = ctx.store("identical content")
        ref2 = ctx.store("identical content")
        hash1 = ref1.split("[Cached: ")[1].split("]")[0]
        hash2 = ref2.split("[Cached: ")[1].split("]")[0]
        assert hash1 == hash2

    def test_size_in_reference(self, ctx: FileContext) -> None:
        content = "x" * 100
        ref = ctx.store(content)
        assert "[Size: 100 chars]" in ref

    def test_cache_dir_created_on_init(self, tmp_path) -> None:
        cache_dir = tmp_path / "new_cache"
        assert not cache_dir.exists()
        FileContext(cache_dir=cache_dir)
        assert cache_dir.exists()


# ═══════════════════════════════════════════════════════════════
# Integration-style: combined CC validation
# ═══════════════════════════════════════════════════════════════


class TestCompletionCriteria:
    """End-to-end validation of all 4 Completion Criteria."""

    def test_cc1_prefix_stable_128_tokens(self) -> None:
        """CC#1: first ~128 tokens (chars as proxy) are always identical."""
        opt = KVCacheOptimizer()
        prompts = [
            opt.build_system_prompt(),
            opt.build_system_prompt({"goal": "A"}),
            opt.build_system_prompt({"goal": "B", "step": 99}),
            opt.build_system_prompt({"x": list(range(50))}),
        ]
        # Use 128 chars as proxy for ~128 tokens
        first_128 = [p[:128] for p in prompts]
        assert len(set(first_128)) == 1

    def test_cc2_tool_count_invariant(self) -> None:
        """CC#2: tool definition count does not change during execution."""
        tools = [ToolDefinition(name=f"tool_{i}") for i in range(10)]
        sm = ToolStateMachine(tools)
        initial = sm.total_count

        sm.mask("tool_0")
        sm.mask("tool_5")
        sm.mask_by_prefix("tool_7")
        sm.unmask("tool_0")
        sm.mask_by_prefix("tool_")
        sm.unmask_by_prefix("tool_")

        assert sm.total_count == initial
        assert len(sm.get_all_tools()) == initial

    def test_cc3_todo_auto_updated(self, tmp_path) -> None:
        """CC#3: todo.md changes before/after task execution."""
        manager = FileTodoManager(tmp_path / "todo.md")
        s1 = SubTask(description="Step 1")
        s2 = SubTask(description="Step 2")
        task = TaskEntity(goal="CC3 test", subtasks=[s1, s2])

        # Before execution
        manager.update_from_task(task)
        before = manager.read()
        assert "[ ] Step 1" in before
        assert "0%" in before

        # After execution
        s1.status = SubTaskStatus.SUCCESS
        s2.status = SubTaskStatus.SUCCESS
        manager.update_from_task(task)
        after = manager.read()
        assert "[x] Step 1" in after
        assert "[x] Step 2" in after
        assert "100%" in after

        assert before != after

    def test_cc4_three_consecutive_diverse(self) -> None:
        """CC#4: 3 consecutive similar observations → 3 different formats."""
        div = ObservationDiversifier()
        obs = {"result": "same result", "status": "success"}
        f0 = div.serialize(obs, 0)
        f1 = div.serialize(obs, 1)
        f2 = div.serialize(obs, 2)
        assert f0 != f1
        assert f1 != f2
        assert f0 != f2

    def test_cc1_and_cc5_combined(self) -> None:
        """KV-cache prefix is stable even when observation format varies."""
        opt = KVCacheOptimizer()
        div = ObservationDiversifier()

        obs = {"result": "data", "status": "ok"}
        for i in range(10):
            formatted = div.serialize(obs, i)
            prompt = opt.build_system_prompt({"observation": formatted})
            assert opt.validate_prefix_stability(prompt)

"""Tests for Sprint 13.3 — Dynamic Agent Role Assignment in task engine.

Tests: role injection into execution prompts, role display in discussion,
backward compatibility when no roles assigned.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.entities.react_trace import ReactTrace
from domain.entities.task import SubTask, TaskEntity
from domain.ports.agent_engine import AgentEngineResult
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.status import SubTaskStatus
from domain.value_objects.task_complexity import TaskComplexity
from infrastructure.task_graph.engine import LangGraphTaskEngine
from infrastructure.task_graph.react_executor import ReactResult


def _make_engine(
    route_to_engine=None,
    react_result=None,
    llm_content: str = "response",
) -> LangGraphTaskEngine:
    """Build a test engine with mocked dependencies."""
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value=MagicMock(content=llm_content, model="test-model", cost_usd=0.01)
    )
    llm.is_available = AsyncMock(return_value=False)

    analyzer = AsyncMock()
    analyzer.decompose = AsyncMock(return_value=[SubTask(description="test")])

    react = AsyncMock()
    if react_result:
        react.execute = AsyncMock(return_value=react_result)
    else:
        react.execute = AsyncMock(
            return_value=ReactResult(
                trace=ReactTrace(),
                final_answer="answer",
                total_cost_usd=0.01,
                model_used="test-model",
            )
        )

    return LangGraphTaskEngine(
        llm=llm,
        analyzer=analyzer,
        react_executor=react,
        route_to_engine=route_to_engine,
    )


class TestRoleInSubTask:
    """SubTask entity supports role field."""

    def test_default_role_is_none(self) -> None:
        st = SubTask(description="test task")
        assert st.role is None

    def test_role_can_be_set(self) -> None:
        st = SubTask(description="test task", role="critical reviewer")
        assert st.role == "critical reviewer"

    def test_role_japanese(self) -> None:
        st = SubTask(description="テスト", role="賛成派")
        assert st.role == "賛成派"

    def test_role_assignment(self) -> None:
        st = SubTask(description="test")
        st.role = "data analyst"
        assert st.role == "data analyst"


class TestRoleInEngineRouting:
    """Role context is prepended to engine task prompt."""

    @pytest.mark.asyncio
    async def test_role_injected_into_engine_task(self) -> None:
        """When subtask has a role, engine receives role-prefixed prompt."""
        engine_result = AgentEngineResult(
            engine=AgentEngineType.CLAUDE_CODE,
            success=True,
            output="engine output",
            model_used="claude-sonnet-4-6",
        )
        route = AsyncMock()
        route.execute = AsyncMock(return_value=engine_result)

        engine = _make_engine(route_to_engine=route)
        task = TaskEntity(
            goal="analyze market",
            subtasks=[
                SubTask(
                    description="analyze trends",
                    preferred_model="claude-sonnet-4-6",
                    complexity=TaskComplexity.MEDIUM,
                    role="financial analyst",
                ),
            ],
        )
        await engine.execute(task)

        # Verify engine received role-prefixed task
        call_kwargs = route.execute.call_args
        task_text = call_kwargs.kwargs.get("task") or call_kwargs[1].get("task", "")
        assert "financial analyst" in task_text
        assert "acting as" in task_text.lower()

    @pytest.mark.asyncio
    async def test_no_role_no_prefix(self) -> None:
        """When subtask has no role, engine receives clean prompt."""
        engine_result = AgentEngineResult(
            engine=AgentEngineType.CLAUDE_CODE,
            success=True,
            output="engine output",
            model_used="claude-sonnet-4-6",
        )
        route = AsyncMock()
        route.execute = AsyncMock(return_value=engine_result)

        engine = _make_engine(route_to_engine=route)
        task = TaskEntity(
            goal="test",
            subtasks=[
                SubTask(
                    description="do test",
                    preferred_model="claude-sonnet-4-6",
                    complexity=TaskComplexity.MEDIUM,
                ),
            ],
        )
        await engine.execute(task)

        call_kwargs = route.execute.call_args
        task_text = call_kwargs.kwargs.get("task") or call_kwargs[1].get("task", "")
        assert "acting as" not in task_text.lower()


class TestRoleInReactPath:
    """Role context is prepended to ReAct system prompt."""

    @pytest.mark.asyncio
    async def test_role_in_react_system_prompt(self) -> None:
        react_result = ReactResult(
            trace=ReactTrace(),
            final_answer="answer",
            total_cost_usd=0.01,
            model_used="test-model",
        )
        react = AsyncMock()
        react.execute = AsyncMock(return_value=react_result)

        engine = _make_engine(react_result=react_result)
        engine._react = react  # replace with our mock

        task = TaskEntity(
            goal="analyze data",
            subtasks=[
                SubTask(
                    description="search for data",
                    complexity=TaskComplexity.MEDIUM,
                    role="data collector",
                ),
            ],
        )
        await engine.execute(task)

        call_kwargs = react.execute.call_args
        system_prompt = call_kwargs.kwargs.get("system_prompt", "")
        assert "data collector" in system_prompt
        assert "acting as" in system_prompt.lower()


class TestRoleInLegacyPath:
    """Role context is prepended in direct LLM completion path."""

    @pytest.mark.asyncio
    async def test_role_in_legacy_system_prompt(self) -> None:
        engine = _make_engine()
        engine._react = None  # force legacy path

        task = TaskEntity(
            goal="write poem",
            subtasks=[
                SubTask(
                    description="compose haiku",
                    complexity=TaskComplexity.SIMPLE,
                    role="poet laureate",
                ),
            ],
        )
        await engine.execute(task)

        # Check the LLM was called with role in system prompt
        call_args = engine._llm.complete.call_args
        messages = call_args[0][0] if call_args[0] else call_args.kwargs.get("messages", [])
        system_msg = messages[0]["content"]
        assert "poet laureate" in system_msg
        assert "acting as" in system_msg.lower()


class TestRoleInDiscussion:
    """Discussion phase includes participant roles in model outputs."""

    @pytest.mark.asyncio
    async def test_discussion_includes_roles(self) -> None:
        engine = _make_engine()

        task = TaskEntity(
            goal="analyze AI market",
            subtasks=[
                SubTask(
                    description="subtask A",
                    status=SubTaskStatus.SUCCESS,
                    result="AI is growing fast",
                    model_used="claude-sonnet-4-6",
                    role="optimist",
                ),
                SubTask(
                    description="subtask B",
                    status=SubTaskStatus.SUCCESS,
                    result="AI has risks",
                    model_used="o4-mini",
                    role="pessimist",
                ),
            ],
        )
        engine._task = task

        # Capture the synthesis LLM call
        state = {"cost_so_far": 0.0, "history": [], "ready_ids": [], "status": "running"}
        await engine._run_discussion(state)

        # Verify synthesis LLM was called with role tags
        call_args = engine._llm.complete.call_args
        messages = call_args[0][0] if call_args[0] else call_args.kwargs.get("messages", [])
        system_msg = messages[0]["content"]
        assert "role: optimist" in system_msg
        assert "role: pessimist" in system_msg

    @pytest.mark.asyncio
    async def test_discussion_without_roles_backward_compat(self) -> None:
        """Discussion works when subtasks have no roles (backward compat)."""
        engine = _make_engine()

        task = TaskEntity(
            goal="test task",
            subtasks=[
                SubTask(
                    description="sub A",
                    status=SubTaskStatus.SUCCESS,
                    result="result A",
                    model_used="model-a",
                ),
                SubTask(
                    description="sub B",
                    status=SubTaskStatus.SUCCESS,
                    result="result B",
                    model_used="model-b",
                ),
            ],
        )
        engine._task = task

        state = {"cost_so_far": 0.0, "history": [], "ready_ids": [], "status": "running"}
        cost = await engine._run_discussion(state)

        # Should complete without error
        assert cost >= 0.0
        # Synthesis subtask should be created
        assert len(task.subtasks) == 3
        assert task.subtasks[-1].status == SubTaskStatus.SUCCESS

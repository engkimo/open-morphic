"""Tests for LangGraphTaskEngine Two Worlds integration (Sprints 12.1-12.6).

Tests: auto-upgrade, DEGRADED validation, tools_used stamping, engine routing,
discussion phase.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.entities.react_trace import ReactStep, ReactTrace, ToolCallRecord
from domain.entities.task import SubTask, TaskEntity
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.status import SubTaskStatus
from domain.value_objects.task_complexity import TaskComplexity
from infrastructure.task_graph.engine import (
    LangGraphTaskEngine,
    _infer_engine_from_model,
    _resolve_engine_type,
)
from infrastructure.task_graph.react_executor import ReactExecutor, ReactResult


def _make_engine(
    react_result: ReactResult | list[ReactResult] | None = None,
    llm_content: str = "response",
    route_to_engine: Any = None,
) -> LangGraphTaskEngine:
    """Build a test engine with mocked dependencies."""
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value=MagicMock(content=llm_content, model="test-model", cost_usd=0.01)
    )

    analyzer = AsyncMock()
    analyzer.decompose = AsyncMock(return_value=[SubTask(description="test")])

    react = AsyncMock(spec=ReactExecutor)
    if isinstance(react_result, list):
        react.execute = AsyncMock(side_effect=react_result)
    elif react_result is not None:
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


def _react_result_with_tools(
    tools: list[str],
    model: str = "test-model",
    data_sources: list[str] | None = None,
) -> ReactResult:
    """Build a ReactResult that recorded tool usage."""
    steps = [
        ReactStep(
            step_number=0,
            tool_calls=[ToolCallRecord(id=f"tc_{t}", tool_name=t, arguments={}) for t in tools],
            observations=["result"] * len(tools),
        )
    ]
    return ReactResult(
        trace=ReactTrace(steps=steps, final_answer="Found results"),
        final_answer="Found results",
        total_cost_usd=0.05,
        model_used=model,
        tools_used=tools or None,
        data_sources=data_sources,
    )


def _react_result_no_tools(model: str = "ollama/qwen3:8b") -> ReactResult:
    """Build a ReactResult with no tool calls (text-only)."""
    return ReactResult(
        trace=ReactTrace(
            steps=[ReactStep(step_number=0, thought="thinking")],
            final_answer="I think the answer is...",
        ),
        final_answer="I think the answer is...",
        total_cost_usd=0.0,
        model_used=model,
    )


# ══════════════════════════════════════════════════════════════════
# Model → Engine mapping
# ══════════════════════════════════════════════════════════════════


class TestResolveEngineType:
    def test_claude_model(self) -> None:
        assert _resolve_engine_type("claude-sonnet-4-6") == AgentEngineType.CLAUDE_CODE

    def test_gpt_model(self) -> None:
        assert _resolve_engine_type("o4-mini") == AgentEngineType.CODEX_CLI

    def test_gemini_prefix(self) -> None:
        assert _resolve_engine_type("gemini/gemini-2.5-flash") == AgentEngineType.GEMINI_CLI

    def test_ollama_prefix(self) -> None:
        assert _resolve_engine_type("ollama/qwen3:8b") == AgentEngineType.OLLAMA

    def test_none(self) -> None:
        assert _resolve_engine_type(None) is None

    def test_unknown(self) -> None:
        assert _resolve_engine_type("unknown-model") is None


class TestInferEngineFromModel:
    """TD-158: _infer_engine_from_model for UI engine_used labels."""

    def test_ollama_prefix(self) -> None:
        assert _infer_engine_from_model("ollama/qwen3:8b") == "ollama"

    def test_ollama_bare_model(self) -> None:
        assert _infer_engine_from_model("qwen3:8b") == "ollama"

    def test_claude(self) -> None:
        assert _infer_engine_from_model("claude-sonnet-4-6") == "anthropic"

    def test_gemini(self) -> None:
        assert _infer_engine_from_model("gemini/gemini-2.5-flash") == "google"

    def test_gpt(self) -> None:
        assert _infer_engine_from_model("gpt-4o") == "openai"

    def test_o4_mini(self) -> None:
        assert _infer_engine_from_model("o4-mini") == "openai"

    def test_none(self) -> None:
        assert _infer_engine_from_model(None) == "ollama"

    def test_unknown(self) -> None:
        assert _infer_engine_from_model("some-random-model") == "litellm"


# ══════════════════════════════════════════════════════════════════
# Sprint 12.1: tools_used stamping
# ══════════════════════════════════════════════════════════════════


class TestToolsUsedStamping:
    @pytest.mark.asyncio
    async def test_tools_stamped_on_subtask(self) -> None:
        """ReAct result tools_used should be stamped on the subtask."""
        result = _react_result_with_tools(
            ["web_search", "web_fetch"],
            data_sources=["https://example.com"],
        )
        engine = _make_engine(react_result=result)

        task = TaskEntity(
            goal="Search for tickets",
            subtasks=[
                SubTask(
                    description="Search for movie tickets",
                    complexity=TaskComplexity.MEDIUM,
                )
            ],
        )
        executed = await engine.execute(task)

        st = executed.subtasks[0]
        assert st.tools_used == ["web_search", "web_fetch"]
        assert st.data_sources == ["https://example.com"]


# ══════════════════════════════════════════════════════════════════
# Sprint 12.5: DEGRADED validation
# ══════════════════════════════════════════════════════════════════


class TestDegradedValidation:
    @pytest.mark.asyncio
    async def test_tool_requiring_no_tools_is_degraded(self) -> None:
        """Subtask requiring tools but with no tools_used → DEGRADED."""
        result = _react_result_no_tools()
        engine = _make_engine(react_result=result)

        task = TaskEntity(
            goal="映画チケットを検索して",
            subtasks=[
                SubTask(
                    description="映画チケットを検索して",
                    complexity=TaskComplexity.MEDIUM,
                )
            ],
        )
        executed = await engine.execute(task)
        assert executed.subtasks[0].status == SubTaskStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_simple_task_stays_success(self) -> None:
        """Simple task (no tools needed) should stay SUCCESS."""
        result = _react_result_no_tools()
        engine = _make_engine(react_result=result)

        task = TaskEntity(
            goal="1+1は？",
            subtasks=[SubTask(description="1+1は？", complexity=TaskComplexity.SIMPLE)],
        )
        executed = await engine.execute(task)
        assert executed.subtasks[0].status == SubTaskStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_tool_requiring_with_tools_stays_success(self) -> None:
        """Tool-requiring task WITH tools used → stays SUCCESS."""
        result = _react_result_with_tools(["web_search"])
        engine = _make_engine(react_result=result)

        task = TaskEntity(
            goal="映画チケットを検索して",
            subtasks=[
                SubTask(
                    description="映画チケットを検索して",
                    complexity=TaskComplexity.MEDIUM,
                )
            ],
        )
        executed = await engine.execute(task)
        assert executed.subtasks[0].status == SubTaskStatus.SUCCESS


# ══════════════════════════════════════════════════════════════════
# Sprint 12.6: Auto-upgrade
# ══════════════════════════════════════════════════════════════════


class TestAutoUpgrade:
    @pytest.mark.asyncio
    async def test_auto_upgrade_when_ollama_cant_tool_call(self) -> None:
        """When Ollama produces no tool calls for a tool-requiring task,
        engine should auto-upgrade to a cloud model."""
        # First call: Ollama returns no tool calls
        # Second call: Cloud model returns with tools
        first = _react_result_no_tools(model="ollama/qwen3:8b")
        second = _react_result_with_tools(["web_search"], model="claude-sonnet-4-6")

        engine = _make_engine(react_result=[first, second])

        task = TaskEntity(
            goal="映画チケットを検索して",
            subtasks=[
                SubTask(
                    description="映画チケットを検索して",
                    complexity=TaskComplexity.MEDIUM,
                )
            ],
        )
        executed = await engine.execute(task)

        st = executed.subtasks[0]
        # Should have used the upgraded model
        assert st.model_used == "claude-sonnet-4-6"
        assert st.tools_used == ["web_search"]
        assert st.status == SubTaskStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_no_upgrade_when_preferred_model_set(self) -> None:
        """If preferred_model is explicitly set, don't auto-upgrade."""
        result = _react_result_no_tools(model="ollama/qwen3:8b")
        engine = _make_engine(react_result=result)

        task = TaskEntity(
            goal="映画チケットを検索して",
            subtasks=[
                SubTask(
                    description="映画チケットを検索して",
                    complexity=TaskComplexity.MEDIUM,
                    preferred_model="ollama/qwen3:8b",
                )
            ],
        )
        executed = await engine.execute(task)
        # Should NOT auto-upgrade, but mark as DEGRADED
        assert executed.subtasks[0].status == SubTaskStatus.DEGRADED


# ══════════════════════════════════════════════════════════════════
# Sprint 12.2: Per-engine routing
# ══════════════════════════════════════════════════════════════════


class TestPerEngineRouting:
    @pytest.mark.asyncio
    async def test_cloud_model_routes_to_engine(self) -> None:
        """Cloud model preference routes through engine driver (autonomous agent)."""
        from domain.ports.agent_engine import AgentEngineResult

        route = AsyncMock()
        route.execute = AsyncMock(
            return_value=AgentEngineResult(
                engine=AgentEngineType.CLAUDE_CODE,
                success=True,
                output="engine analysis",
                cost_usd=0.05,
                model_used="claude-sonnet-4-6",
            )
        )
        react_result = _react_result_no_tools(model="claude-sonnet-4-6")
        engine = _make_engine(
            react_result=react_result,
            route_to_engine=route,
        )

        task = TaskEntity(
            goal="Analyze architecture",
            subtasks=[
                SubTask(
                    description="Analyze",
                    complexity=TaskComplexity.MEDIUM,
                    preferred_model="claude-sonnet-4-6",
                )
            ],
        )
        executed = await engine.execute(task)

        st = executed.subtasks[0]
        # Engine driver handles execution as autonomous agent
        assert st.model_used == "claude-sonnet-4-6"
        assert st.engine_used == "claude_code"
        route.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_ollama_model_routes_to_engine(self) -> None:
        """Ollama models also route through engine driver for consistency."""
        from domain.ports.agent_engine import AgentEngineResult

        route = AsyncMock()
        route.execute = AsyncMock(
            return_value=AgentEngineResult(
                engine=AgentEngineType.OLLAMA,
                success=True,
                output="ollama answer",
                cost_usd=0.0,
                model_used="ollama/qwen3:8b",
            )
        )
        engine = _make_engine(route_to_engine=route)

        task = TaskEntity(
            goal="Simple question",
            subtasks=[
                SubTask(
                    description="Simple question",
                    complexity=TaskComplexity.SIMPLE,
                    preferred_model="ollama/qwen3:8b",
                )
            ],
        )
        executed = await engine.execute(task)
        st = executed.subtasks[0]
        assert st.engine_used == "ollama"
        route.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_preferred_model_simple_qa_skips_engine_route(self) -> None:
        """SIMPLE_QA subtask (no topic match) stays on local LLM, no engine route.

        TD-155: Auto-route classifies subtasks — only SIMPLE_QA/FILE_OP → OLLAMA
        skip engine routing. Use a generic description that won't match any topic.
        """
        route = AsyncMock()
        react_result = _react_result_no_tools(model="ollama/qwen3:8b")
        engine = _make_engine(
            react_result=react_result,
            route_to_engine=route,
        )

        task = TaskEntity(
            goal="Simple computation",
            subtasks=[
                SubTask(
                    description="Calculate the answer",
                    complexity=TaskComplexity.MEDIUM,
                )
            ],
        )
        executed = await engine.execute(task)
        assert executed.subtasks[0].model_used == "ollama/qwen3:8b"
        route.execute.assert_not_called()


# ══════════════════════════════════════════════════════════════════
# Sprint 12.3: Discussion phase
# ══════════════════════════════════════════════════════════════════


class TestDiscussionPhase:
    @pytest.mark.asyncio
    async def test_multi_model_triggers_discussion(self) -> None:
        """When multiple models are used, a synthesis subtask should be created."""
        llm = AsyncMock()
        llm.complete = AsyncMock(
            return_value=MagicMock(
                content="Synthesized answer",
                model="synthesis-model",
                cost_usd=0.02,
            )
        )

        analyzer = AsyncMock()
        react = AsyncMock(spec=ReactExecutor)

        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer, react_executor=react)

        task = TaskEntity(
            goal="Multi-model task",
            subtasks=[
                SubTask(
                    description="A",
                    status=SubTaskStatus.SUCCESS,
                    result="Result from Claude",
                    model_used="claude-sonnet-4-6",
                    complexity=TaskComplexity.MEDIUM,
                ),
                SubTask(
                    description="B",
                    status=SubTaskStatus.SUCCESS,
                    result="Result from GPT",
                    model_used="o4-mini",
                    complexity=TaskComplexity.MEDIUM,
                ),
            ],
        )

        # Manually test _finalize which includes discussion
        engine._task = task
        state = {"cost_so_far": 0.1, "ready_ids": [], "history": [], "status": "running"}
        await engine._finalize(state)

        # Should have added a synthesis subtask
        assert len(task.subtasks) == 3
        synthesis = task.subtasks[2]
        assert "[Discussion]" in synthesis.description
        assert synthesis.status == SubTaskStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_single_model_no_discussion(self) -> None:
        """Single model tasks should NOT trigger discussion."""
        llm = AsyncMock()
        analyzer = AsyncMock()
        react = AsyncMock(spec=ReactExecutor)

        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer, react_executor=react)

        task = TaskEntity(
            goal="Single model",
            subtasks=[
                SubTask(
                    description="A",
                    status=SubTaskStatus.SUCCESS,
                    result="Answer",
                    model_used="ollama/qwen3:8b",
                    complexity=TaskComplexity.SIMPLE,
                ),
            ],
        )

        engine._task = task
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}
        await engine._finalize(state)

        # No synthesis subtask added
        assert len(task.subtasks) == 1


# ══════════════════════════════════════════════════════════════════
# Sprint 13.1: Iterative multi-round discussion
# ══════════════════════════════════════════════════════════════════


def _make_multi_model_task() -> TaskEntity:
    """Create a task with 2 completed subtasks from different models."""
    return TaskEntity(
        goal="Multi-agent task",
        subtasks=[
            SubTask(
                description="A",
                status=SubTaskStatus.SUCCESS,
                result="Result from Claude",
                model_used="claude-sonnet-4-6",
                complexity=TaskComplexity.MEDIUM,
            ),
            SubTask(
                description="B",
                status=SubTaskStatus.SUCCESS,
                result="Result from GPT",
                model_used="o4-mini",
                complexity=TaskComplexity.MEDIUM,
            ),
        ],
    )


class TestIterativeDiscussion:
    @pytest.mark.asyncio
    async def test_single_round_backward_compat(self) -> None:
        """discussion_max_rounds=1 produces same behavior as original."""
        llm = AsyncMock()
        llm.complete = AsyncMock(
            return_value=MagicMock(
                content="Synthesis R1",
                model="ollama/qwen3:8b",
                cost_usd=0.0,
            )
        )
        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            discussion_max_rounds=1,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        assert len(engine._task.subtasks) == 3
        synthesis = engine._task.subtasks[2]
        assert "[Discussion]" in synthesis.description
        assert synthesis.result == "Synthesis R1"
        # No round label when max_rounds=1
        assert "R1" not in synthesis.description

    @pytest.mark.asyncio
    async def test_two_rounds_produces_refined_synthesis(self) -> None:
        """discussion_max_rounds=2 runs two rounds, final result is from round 2."""
        responses = [
            MagicMock(content="Initial synthesis", model="ollama/qwen3:8b", cost_usd=0.0),
            MagicMock(content="Refined synthesis", model="claude-sonnet-4-6", cost_usd=0.05),
        ]
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=responses)
        llm.is_available = AsyncMock(return_value=True)

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            discussion_max_rounds=2,
            discussion_rotate_models=True,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        assert len(engine._task.subtasks) == 3
        synthesis = engine._task.subtasks[2]
        assert "R2" in synthesis.description
        assert synthesis.result == "Refined synthesis"
        assert synthesis.cost_usd == 0.05  # total of both rounds
        assert llm.complete.await_count == 2

    @pytest.mark.asyncio
    async def test_rotate_models_uses_different_model_in_round_2(self) -> None:
        """Round 2 should request a different model via _pick_discussion_model."""
        responses = [
            MagicMock(content="R1", model="ollama/qwen3:8b", cost_usd=0.0),
            MagicMock(content="R2", model="claude-sonnet-4-6", cost_usd=0.05),
        ]
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=responses)
        llm.is_available = AsyncMock(return_value=True)

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            discussion_max_rounds=2,
            discussion_rotate_models=True,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        # Round 1: model=None (default, LOCAL_FIRST)
        # Round 2: model="claude-sonnet-4-6" (rotated)
        calls = llm.complete.call_args_list
        assert calls[0].kwargs.get("model") is None
        assert calls[1].kwargs.get("model") == "claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_rotate_disabled_uses_default_both_rounds(self) -> None:
        """When discussion_rotate_models=False, all rounds use default model."""
        responses = [
            MagicMock(content="R1", model="ollama/qwen3:8b", cost_usd=0.0),
            MagicMock(content="R2", model="ollama/qwen3:8b", cost_usd=0.0),
        ]
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=responses)

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            discussion_max_rounds=2,
            discussion_rotate_models=False,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        calls = llm.complete.call_args_list
        assert calls[0].kwargs.get("model") is None
        assert calls[1].kwargs.get("model") is None

    @pytest.mark.asyncio
    async def test_three_rounds(self) -> None:
        """3-round discussion produces result from final round."""
        responses = [
            MagicMock(content="R1", model="ollama/qwen3:8b", cost_usd=0.0),
            MagicMock(content="R2", model="claude-sonnet-4-6", cost_usd=0.03),
            MagicMock(content="R3 final", model="o4-mini", cost_usd=0.02),
        ]
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=responses)
        llm.is_available = AsyncMock(return_value=True)

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            discussion_max_rounds=3,
            discussion_rotate_models=True,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        synthesis = engine._task.subtasks[2]
        assert "R3" in synthesis.description
        assert synthesis.result == "R3 final"
        assert synthesis.cost_usd == 0.05  # 0 + 0.03 + 0.02
        assert llm.complete.await_count == 3

    @pytest.mark.asyncio
    async def test_round_failure_stops_early(self) -> None:
        """If a discussion round fails, stop and use last successful result."""
        llm = AsyncMock()
        llm.complete = AsyncMock(
            side_effect=[
                MagicMock(content="R1 OK", model="ollama/qwen3:8b", cost_usd=0.0),
                Exception("API error"),
            ]
        )
        llm.is_available = AsyncMock(return_value=True)

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            discussion_max_rounds=3,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        # Should still produce synthesis from Round 1
        assert len(engine._task.subtasks) == 3
        synthesis = engine._task.subtasks[2]
        assert synthesis.result == "R1 OK"

    @pytest.mark.asyncio
    async def test_no_cloud_model_available_falls_back(self) -> None:
        """When no cloud model available, round 2 still runs with default model."""
        responses = [
            MagicMock(content="R1", model="ollama/qwen3:8b", cost_usd=0.0),
            MagicMock(content="R2", model="ollama/qwen3:8b", cost_usd=0.0),
        ]
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=responses)
        llm.is_available = AsyncMock(return_value=False)  # no cloud models

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            discussion_max_rounds=2,
            discussion_rotate_models=True,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        # Round 2 falls back to default (model=None)
        calls = llm.complete.call_args_list
        assert calls[1].kwargs.get("model") is None
        assert engine._task.subtasks[2].result == "R2"

    @pytest.mark.asyncio
    async def test_critique_prompt_used_in_round_2(self) -> None:
        """Round 2 should use the critique prompt, not the synthesis prompt."""
        responses = [
            MagicMock(content="R1 synthesis", model="ollama/qwen3:8b", cost_usd=0.0),
            MagicMock(content="R2 critique", model="claude-sonnet-4-6", cost_usd=0.05),
        ]
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=responses)
        llm.is_available = AsyncMock(return_value=True)

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            discussion_max_rounds=2,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        # Round 2 system prompt should contain the critique instructions
        round2_call = llm.complete.call_args_list[1]
        system_prompt = round2_call.args[0][0]["content"]
        assert "critical reviewer" in system_prompt
        assert "R1 synthesis" in system_prompt  # previous synthesis injected

    @pytest.mark.asyncio
    async def test_min_rounds_clamped_to_1(self) -> None:
        """discussion_max_rounds < 1 is clamped to 1."""
        engine = LangGraphTaskEngine(
            llm=AsyncMock(),
            analyzer=AsyncMock(),
            discussion_max_rounds=0,
        )
        assert engine._discussion_max_rounds == 1

        engine2 = LangGraphTaskEngine(
            llm=AsyncMock(),
            analyzer=AsyncMock(),
            discussion_max_rounds=-5,
        )
        assert engine2._discussion_max_rounds == 1


# ══════════════════════════════════════════════════════════════════
# Sprint 13.2: Engine-Routed Discussion
# ══════════════════════════════════════════════════════════════════


def _make_engine_result(
    output: str = "Engine synthesis",
    model_used: str = "claude-sonnet-4-6",
    engine: AgentEngineType = AgentEngineType.CLAUDE_CODE,
    cost: float = 0.05,
    success: bool = True,
) -> MagicMock:
    """Create a mock AgentEngineResult."""
    return MagicMock(
        success=success,
        output=output,
        model_used=model_used,
        engine=engine,
        cost_usd=cost,
    )


class TestEngineRoutedDiscussion:
    @pytest.mark.asyncio
    async def test_engine_routed_round2_uses_engine(self) -> None:
        """When route_to_engine is available and model maps to an engine,
        discussion round 2 should use engine routing."""
        # Round 1: LLM (default, no model → no engine)
        llm = AsyncMock()
        llm.complete = AsyncMock(
            return_value=MagicMock(
                content="R1 LLM synthesis",
                model="ollama/qwen3:8b",
                cost_usd=0.0,
            )
        )
        llm.is_available = AsyncMock(return_value=True)

        # Round 2: engine should be tried first
        route_mock = AsyncMock()
        route_mock.execute = AsyncMock(
            return_value=_make_engine_result(
                output="R2 Engine critique",
                model_used="claude-sonnet-4-6",
                cost=0.06,
            )
        )

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            route_to_engine=route_mock,
            discussion_max_rounds=2,
            discussion_rotate_models=True,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        synthesis = engine._task.subtasks[2]
        assert synthesis.result == "R2 Engine critique"
        assert synthesis.engine_used == "claude_code"
        assert "via claude_code" in synthesis.description
        assert route_mock.execute.await_count == 1
        # Round 1 used LLM (no engine type for None model)
        assert llm.complete.await_count == 1

    @pytest.mark.asyncio
    async def test_engine_failure_falls_back_to_llm(self) -> None:
        """If engine routing fails, discussion should fall back to LLM API."""
        llm = AsyncMock()
        llm.complete = AsyncMock(
            side_effect=[
                MagicMock(content="R1 LLM", model="ollama/qwen3:8b", cost_usd=0.0),
                MagicMock(content="R2 LLM fallback", model="claude-sonnet-4-6", cost_usd=0.04),
            ]
        )
        llm.is_available = AsyncMock(return_value=True)

        route_mock = AsyncMock()
        route_mock.execute = AsyncMock(
            return_value=_make_engine_result(success=False, output="error")
        )

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            route_to_engine=route_mock,
            discussion_max_rounds=2,
            discussion_rotate_models=True,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        synthesis = engine._task.subtasks[2]
        assert synthesis.result == "R2 LLM fallback"
        assert synthesis.engine_used is None
        # Both rounds used LLM (Round 2 engine failed → LLM fallback)
        assert llm.complete.await_count == 2

    @pytest.mark.asyncio
    async def test_engine_exception_falls_back_to_llm(self) -> None:
        """Engine exception should not crash — falls back to LLM."""
        llm = AsyncMock()
        llm.complete = AsyncMock(
            side_effect=[
                MagicMock(content="R1", model="ollama/qwen3:8b", cost_usd=0.0),
                MagicMock(content="R2 fallback", model="claude-sonnet-4-6", cost_usd=0.03),
            ]
        )
        llm.is_available = AsyncMock(return_value=True)

        route_mock = AsyncMock()
        route_mock.execute = AsyncMock(side_effect=Exception("engine crash"))

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            route_to_engine=route_mock,
            discussion_max_rounds=2,
            discussion_rotate_models=True,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        synthesis = engine._task.subtasks[2]
        assert synthesis.result == "R2 fallback"
        assert synthesis.engine_used is None

    @pytest.mark.asyncio
    async def test_no_route_to_engine_uses_llm_only(self) -> None:
        """Without route_to_engine, all rounds use LLM (backward compat)."""
        llm = AsyncMock()
        llm.complete = AsyncMock(
            side_effect=[
                MagicMock(content="R1", model="ollama/qwen3:8b", cost_usd=0.0),
                MagicMock(content="R2", model="claude-sonnet-4-6", cost_usd=0.04),
            ]
        )
        llm.is_available = AsyncMock(return_value=True)

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            route_to_engine=None,  # No engine routing
            discussion_max_rounds=2,
            discussion_rotate_models=True,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        synthesis = engine._task.subtasks[2]
        assert synthesis.result == "R2"
        assert synthesis.engine_used is None
        assert "via" not in synthesis.description
        assert llm.complete.await_count == 2

    @pytest.mark.asyncio
    async def test_engine_routed_cost_tracking(self) -> None:
        """Engine-routed discussion should correctly sum costs across rounds."""
        llm = AsyncMock()
        llm.complete = AsyncMock(
            return_value=MagicMock(content="R1 LLM", model="ollama/qwen3:8b", cost_usd=0.0)
        )
        llm.is_available = AsyncMock(return_value=True)

        route_mock = AsyncMock()
        route_mock.execute = AsyncMock(
            return_value=_make_engine_result(
                output="R2 engine", cost=0.08, model_used="claude-sonnet-4-6"
            )
        )

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            route_to_engine=route_mock,
            discussion_max_rounds=2,
            discussion_rotate_models=True,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.5, "ready_ids": [], "history": [], "status": "running"}

        result = await engine._finalize(state)

        synthesis = engine._task.subtasks[2]
        assert synthesis.cost_usd == pytest.approx(0.08)  # 0.0 (R1) + 0.08 (R2)
        assert result["cost_so_far"] == pytest.approx(0.58)  # 0.5 + 0.08


class TestAdaptiveDiscussion:
    """Sprint 13.5: Adaptive discussion strategy with convergence detection."""

    @pytest.mark.asyncio
    async def test_adaptive_disabled_runs_all_rounds(self) -> None:
        """When discussion_adaptive=False (default), all rounds execute."""
        responses = [
            MagicMock(content="Same answer", model="ollama/qwen3:8b", cost_usd=0.0),
            MagicMock(content="Same answer", model="claude-sonnet-4-6", cost_usd=0.05),
            MagicMock(content="Same answer", model="gemini/gemini-2.5-flash", cost_usd=0.02),
        ]
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=responses)
        llm.is_available = AsyncMock(return_value=True)

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            discussion_max_rounds=3,
            discussion_rotate_models=True,
            discussion_adaptive=False,  # disabled
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        # All 3 rounds should execute even though content is identical
        assert llm.complete.await_count == 3

    @pytest.mark.asyncio
    async def test_adaptive_converged_stops_early(self) -> None:
        """When adaptive=True and rounds converge, stop before max_rounds."""
        responses = [
            MagicMock(
                content="Initial synthesis of the data analysis results",
                model="ollama/qwen3:8b",
                cost_usd=0.0,
            ),
            MagicMock(
                content="Initial synthesis of the data analysis results",
                model="claude-sonnet-4-6",
                cost_usd=0.05,
            ),
            MagicMock(content="SHOULD NOT REACH", model="gemini/gemini-2.5-flash", cost_usd=0.02),
        ]
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=responses)
        llm.is_available = AsyncMock(return_value=True)

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            discussion_max_rounds=3,
            discussion_rotate_models=True,
            discussion_adaptive=True,
            discussion_convergence_threshold=0.85,
            discussion_min_rounds=1,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        # Should stop after round 2 (identical content = converged)
        assert llm.complete.await_count == 2
        synthesis = engine._task.subtasks[2]
        assert "R2" in synthesis.description
        assert synthesis.result != "SHOULD NOT REACH"

    @pytest.mark.asyncio
    async def test_adaptive_divergent_continues(self) -> None:
        """When adaptive=True but rounds diverge, continue to max_rounds."""
        responses = [
            MagicMock(
                content="Redis is the best choice for caching layer design",
                model="ollama/qwen3:8b",
                cost_usd=0.0,
            ),
            MagicMock(
                content="Quantum computing uses superposition for parallel math",
                model="claude-sonnet-4-6",
                cost_usd=0.05,
            ),
            MagicMock(
                content="Database sharding improves horizontal scalability",
                model="gemini/gemini-2.5-flash",
                cost_usd=0.02,
            ),
        ]
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=responses)
        llm.is_available = AsyncMock(return_value=True)

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            discussion_max_rounds=3,
            discussion_rotate_models=True,
            discussion_adaptive=True,
            discussion_convergence_threshold=0.85,
            discussion_min_rounds=1,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        # All 3 rounds should execute (divergent content)
        assert llm.complete.await_count == 3

    @pytest.mark.asyncio
    async def test_adaptive_respects_min_rounds(self) -> None:
        """Convergence check doesn't fire until min_rounds reached."""
        responses = [
            MagicMock(content="Same analysis output", model="ollama/qwen3:8b", cost_usd=0.0),
            MagicMock(content="Same analysis output", model="claude-sonnet-4-6", cost_usd=0.05),
            MagicMock(
                content="Same analysis output", model="gemini/gemini-2.5-flash", cost_usd=0.02
            ),
        ]
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=responses)
        llm.is_available = AsyncMock(return_value=True)

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            discussion_max_rounds=3,
            discussion_rotate_models=True,
            discussion_adaptive=True,
            discussion_convergence_threshold=0.85,
            discussion_min_rounds=3,  # min = max, so always run all rounds
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        # All 3 rounds execute because min_rounds=3
        assert llm.complete.await_count == 3

    @pytest.mark.asyncio
    async def test_adaptive_single_round_no_convergence_check(self) -> None:
        """With max_rounds=1, adaptive has nothing to converge — runs once."""
        llm = AsyncMock()
        llm.complete = AsyncMock(
            return_value=MagicMock(content="Synth", model="ollama/qwen3:8b", cost_usd=0.0)
        )

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            discussion_max_rounds=1,
            discussion_adaptive=True,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        assert llm.complete.await_count == 1
        synthesis = engine._task.subtasks[2]
        assert synthesis.result == "Synth"

    @pytest.mark.asyncio
    async def test_adaptive_threshold_adjustable(self) -> None:
        """Low threshold makes similar-but-not-identical texts converge."""
        responses = [
            MagicMock(
                content="alpha beta gamma delta epsilon zeta eta theta iota kappa",
                model="ollama/qwen3:8b",
                cost_usd=0.0,
            ),
            MagicMock(
                content="alpha beta gamma delta epsilon zeta eta theta lambda mu",
                model="claude-sonnet-4-6",
                cost_usd=0.05,
            ),
            MagicMock(content="SHOULD NOT REACH", model="gemini/gemini-2.5-flash", cost_usd=0.02),
        ]
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=responses)
        llm.is_available = AsyncMock(return_value=True)

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            discussion_max_rounds=3,
            discussion_rotate_models=True,
            discussion_adaptive=True,
            discussion_convergence_threshold=0.5,  # very lenient
            discussion_min_rounds=1,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        # 80% overlap > 0.5 threshold → converges at round 2
        assert llm.complete.await_count == 2

    @pytest.mark.asyncio
    async def test_adaptive_with_engine_routing(self) -> None:
        """Adaptive convergence works with engine-routed discussion rounds."""
        llm = AsyncMock()
        llm.complete = AsyncMock(
            return_value=MagicMock(content="R1 synthesis", model="ollama/qwen3:8b", cost_usd=0.0)
        )
        llm.is_available = AsyncMock(return_value=True)

        route_mock = AsyncMock()
        route_mock.execute = AsyncMock(
            return_value=_make_engine_result(
                output="R1 synthesis", cost=0.08, model_used="claude-sonnet-4-6"
            )
        )

        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=AsyncMock(),
            react_executor=AsyncMock(spec=ReactExecutor),
            route_to_engine=route_mock,
            discussion_max_rounds=3,
            discussion_rotate_models=True,
            discussion_adaptive=True,
            discussion_convergence_threshold=0.85,
            discussion_min_rounds=1,
        )
        engine._task = _make_multi_model_task()
        state = {"cost_so_far": 0.0, "ready_ids": [], "history": [], "status": "running"}

        await engine._finalize(state)

        # R1: LLM (model=None, no engine type) → "R1 synthesis"
        # R2: engine routing → "R1 synthesis" (same text → converged → stop)
        assert llm.complete.await_count == 1  # R1 only
        assert route_mock.execute.await_count == 1  # R2 only
        synthesis = engine._task.subtasks[2]
        assert "R2" in synthesis.description

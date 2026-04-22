"""Tests for ReactExecutor — ReAct loop core."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from domain.entities.execution import Observation
from domain.ports.llm_gateway import LLMResponse, ToolCallResult
from domain.value_objects.status import ObservationStatus
from infrastructure.task_graph.react_executor import ReactExecutor, ReactResult


def _llm_response(
    content: str = "",
    tool_calls: list[ToolCallResult] | None = None,
    cost: float = 0.001,
    model: str = "test-model",
) -> LLMResponse:
    return LLMResponse(
        content=content,
        model=model,
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=cost,
        tool_calls=tool_calls or [],
    )


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.complete_with_tools = AsyncMock()
    return llm


@pytest.fixture
def mock_executor():
    executor = AsyncMock()
    executor.execute = AsyncMock(
        return_value=Observation(status=ObservationStatus.SUCCESS, result="tool output")
    )
    return executor


@pytest.fixture
def react(mock_llm, mock_executor):
    tools = [{"type": "function", "function": {"name": "web_search"}}]
    return ReactExecutor(
        llm=mock_llm, executor=mock_executor, tool_schemas=tools, max_iterations=10
    )


class TestReactExecutor:
    @pytest.mark.asyncio
    async def test_no_tools_returns_immediately(self, react, mock_llm):
        """LLM returns text without tool calls → single step, final answer."""
        mock_llm.complete_with_tools.return_value = _llm_response(content="The answer is 42")

        result = await react.execute("system", "What is 6*7?")

        assert isinstance(result, ReactResult)
        assert result.final_answer == "The answer is 42"
        assert result.trace.total_iterations == 1
        assert result.trace.terminated_reason == "final_answer"
        assert len(result.trace.steps[0].tool_calls) == 0

    @pytest.mark.asyncio
    async def test_single_tool_then_answer(self, react, mock_llm, mock_executor):
        """LLM calls web_search once, then gives final answer."""
        tc = ToolCallResult(id="call_1", tool_name="web_search", arguments={"query": "test"})
        mock_llm.complete_with_tools.side_effect = [
            _llm_response(content="", tool_calls=[tc], cost=0.002),
            _llm_response(content="Found: result X", cost=0.001),
        ]

        result = await react.execute("sys", "search something")

        assert result.final_answer == "Found: result X"
        assert result.trace.total_iterations == 2
        assert result.trace.terminated_reason == "final_answer"
        assert len(result.trace.steps[0].tool_calls) == 1
        assert result.trace.steps[0].tool_calls[0].tool_name == "web_search"
        mock_executor.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiple_tools_one_step(self, react, mock_llm, mock_executor):
        """LLM returns multiple tool calls in a single step."""
        tc1 = ToolCallResult(id="c1", tool_name="web_search", arguments={"query": "a"})
        tc2 = ToolCallResult(id="c2", tool_name="web_search", arguments={"query": "b"})
        mock_llm.complete_with_tools.side_effect = [
            _llm_response(content="", tool_calls=[tc1, tc2], cost=0.003),
            _llm_response(content="Combined answer", cost=0.001),
        ]

        result = await react.execute("sys", "compare a and b")

        assert len(result.trace.steps[0].tool_calls) == 2
        assert mock_executor.execute.await_count == 2
        assert result.final_answer == "Combined answer"

    @pytest.mark.asyncio
    async def test_multi_step_iteration(self, react, mock_llm, mock_executor):
        """LLM needs 3 rounds of tool calls before final answer."""
        # Use different arguments each round to avoid repetitive-loop detection
        tc1 = ToolCallResult(id="c", tool_name="web_search", arguments={"query": "q1"})
        tc2 = ToolCallResult(id="c", tool_name="web_search", arguments={"query": "q2"})
        tc3 = ToolCallResult(id="c", tool_name="web_search", arguments={"query": "q3"})
        mock_llm.complete_with_tools.side_effect = [
            _llm_response(content="", tool_calls=[tc1], cost=0.001),
            _llm_response(content="", tool_calls=[tc2], cost=0.001),
            _llm_response(content="", tool_calls=[tc3], cost=0.001),
            _llm_response(content="Final after 3 rounds", cost=0.001),
        ]

        result = await react.execute("sys", "deep research")

        assert result.trace.total_iterations == 4
        assert result.final_answer == "Final after 3 rounds"

    @pytest.mark.asyncio
    async def test_max_iterations_stops(self, mock_llm, mock_executor):
        """Loop stops at max_iterations even if LLM keeps calling tools."""
        # Use counter to generate different args each call (avoids repeat detection)
        call_counter = {"n": 0}

        def _next_response(*args, **kwargs):
            call_counter["n"] += 1
            tc = ToolCallResult(
                id="c", tool_name="web_search",
                arguments={"query": f"q{call_counter['n']}"},
            )
            return _llm_response(content="", tool_calls=[tc], cost=0.001)

        mock_llm.complete_with_tools.side_effect = _next_response

        react = ReactExecutor(
            llm=mock_llm, executor=mock_executor, tool_schemas=[], max_iterations=3
        )
        result = await react.execute("sys", "infinite loop")

        assert result.trace.total_iterations == 3
        assert result.trace.terminated_reason == "max_iterations"
        # Fallback answer is built from observations (not empty)
        assert "tool output" in result.final_answer
        assert "iteration limit" in result.final_answer.lower()

    @pytest.mark.asyncio
    async def test_max_iterations_fallback_preserves_observations(self, mock_llm, mock_executor):
        """When max_iterations hit, observations from tool calls are preserved."""
        tc = ToolCallResult(id="c", tool_name="web_search", arguments={"query": "q"})
        mock_executor.execute.return_value = Observation(
            status=ObservationStatus.SUCCESS, result="Search result: Tokyo weather is 15°C"
        )
        mock_llm.complete_with_tools.return_value = _llm_response(
            content="", tool_calls=[tc], cost=0.001
        )

        react = ReactExecutor(
            llm=mock_llm, executor=mock_executor, tool_schemas=[], max_iterations=2
        )
        result = await react.execute("sys", "search weather")

        assert "Tokyo weather" in result.final_answer
        assert result.trace.terminated_reason == "max_iterations"

    @pytest.mark.asyncio
    async def test_max_iterations_all_errors_gives_message(self, mock_llm, mock_executor):
        """When all tool observations are errors, a clear message is returned."""
        tc = ToolCallResult(id="c", tool_name="web_search", arguments={"query": "q"})
        mock_executor.execute.return_value = Observation(
            status=ObservationStatus.ERROR, result="Connection refused"
        )
        mock_llm.complete_with_tools.return_value = _llm_response(
            content="", tool_calls=[tc], cost=0.001
        )

        react = ReactExecutor(
            llm=mock_llm, executor=mock_executor, tool_schemas=[], max_iterations=2
        )
        result = await react.execute("sys", "failing task")

        assert result.trace.terminated_reason == "max_iterations"
        assert "No results obtained" in result.final_answer

    @pytest.mark.asyncio
    async def test_tool_error_in_observation(self, react, mock_llm, mock_executor):
        """Tool failure returns ERROR text that LLM can use to recover."""
        tc = ToolCallResult(id="c1", tool_name="web_search", arguments={"query": "test"})
        mock_executor.execute.return_value = Observation(
            status=ObservationStatus.ERROR, result="Connection refused"
        )
        mock_llm.complete_with_tools.side_effect = [
            _llm_response(content="", tool_calls=[tc]),
            _llm_response(content="Could not search, sorry"),
        ]

        result = await react.execute("sys", "search test")

        assert "ERROR" in result.trace.steps[0].observations[0]
        assert result.final_answer == "Could not search, sorry"

    @pytest.mark.asyncio
    async def test_observation_truncation(self, react, mock_llm, mock_executor):
        """Long tool output is truncated to MAX_OBSERVATION_CHARS."""
        tc = ToolCallResult(id="c1", tool_name="web_search", arguments={"query": "big"})
        mock_executor.execute.return_value = Observation(
            status=ObservationStatus.SUCCESS, result="x" * 10000
        )
        mock_llm.complete_with_tools.side_effect = [
            _llm_response(content="", tool_calls=[tc]),
            _llm_response(content="done"),
        ]

        result = await react.execute("sys", "big data")

        obs = result.trace.steps[0].observations[0]
        assert len(obs) <= ReactExecutor.MAX_OBSERVATION_CHARS

    @pytest.mark.asyncio
    async def test_cost_accumulates(self, react, mock_llm):
        """Costs from multiple LLM calls accumulate correctly."""
        tc = ToolCallResult(id="c", tool_name="web_search", arguments={"query": "q"})
        mock_llm.complete_with_tools.side_effect = [
            _llm_response(content="", tool_calls=[tc], cost=0.010),
            _llm_response(content="answer", cost=0.005),
        ]

        result = await react.execute("sys", "test")

        assert abs(result.total_cost_usd - 0.015) < 1e-9

    @pytest.mark.asyncio
    async def test_allowed_tools_filter(self, mock_llm, mock_executor):
        """Allowed tools parameter filters the schema list."""
        schemas = [
            {"type": "function", "function": {"name": "web_search"}},
            {"type": "function", "function": {"name": "shell_exec"}},
            {"type": "function", "function": {"name": "fs_read"}},
        ]
        mock_llm.complete_with_tools.return_value = _llm_response(content="done")

        react = ReactExecutor(llm=mock_llm, executor=mock_executor, tool_schemas=schemas)
        await react.execute("sys", "test", allowed_tools=["web_search"])

        call_args = mock_llm.complete_with_tools.call_args
        tools_passed = call_args.kwargs["tools"]
        assert len(tools_passed) == 1
        assert tools_passed[0]["function"]["name"] == "web_search"


class TestBuildAssistantMessage:
    def test_arguments_are_valid_json(self):
        """tool_call arguments must be JSON strings, not Python repr."""
        import json

        from infrastructure.task_graph.react_executor import ReactExecutor

        class FakeResponse:
            content = ""
            tool_calls = [
                ToolCallResult(id="c1", tool_name="web_search", arguments={"query": "test's value"})
            ]

        msg = ReactExecutor._build_assistant_message(FakeResponse())

        args_str = msg["tool_calls"][0]["function"]["arguments"]
        # Must be valid JSON (double quotes, not single quotes)
        parsed = json.loads(args_str)
        assert parsed == {"query": "test's value"}


class TestRepetitiveToolLoopDetection:
    """TD-180: Detect and stop repetitive tool-call loops."""

    @pytest.mark.asyncio
    async def test_same_call_three_times_stops(self, mock_llm, mock_executor):
        """Same tool+args 3 times in a row → terminated_reason='repetitive_tool_loop'."""
        tc = ToolCallResult(
            id="c", tool_name="system_notify",
            arguments={"title": "Done", "message": "File created"},
        )
        mock_llm.complete_with_tools.return_value = _llm_response(
            content="", tool_calls=[tc], cost=0.001,
        )

        react = ReactExecutor(
            llm=mock_llm, executor=mock_executor, tool_schemas=[], max_iterations=10,
        )
        result = await react.execute("sys", "notify loop")

        assert result.trace.terminated_reason == "repetitive_tool_loop"
        # Should stop after 3 iterations, not 10
        assert result.trace.total_iterations == 3

    @pytest.mark.asyncio
    async def test_different_args_do_not_trigger(self, mock_llm, mock_executor):
        """Different arguments each time → no repetitive detection."""
        calls = [
            ToolCallResult(id="c", tool_name="web_search", arguments={"query": f"q{i}"})
            for i in range(4)
        ]
        mock_llm.complete_with_tools.side_effect = [
            _llm_response(content="", tool_calls=[calls[0]], cost=0.001),
            _llm_response(content="", tool_calls=[calls[1]], cost=0.001),
            _llm_response(content="", tool_calls=[calls[2]], cost=0.001),
            _llm_response(content="", tool_calls=[calls[3]], cost=0.001),
            _llm_response(content="Final answer", cost=0.001),
        ]

        react = ReactExecutor(
            llm=mock_llm, executor=mock_executor, tool_schemas=[], max_iterations=10,
        )
        result = await react.execute("sys", "diverse queries")

        assert result.trace.terminated_reason == "final_answer"
        assert result.trace.total_iterations == 5

    @pytest.mark.asyncio
    async def test_multi_tool_calls_reset_counter(self, mock_llm, mock_executor):
        """Multiple tool calls in one step reset the repetition counter."""
        tc1 = ToolCallResult(id="c1", tool_name="web_search", arguments={"query": "a"})
        tc2 = ToolCallResult(id="c2", tool_name="web_search", arguments={"query": "b"})
        mock_llm.complete_with_tools.side_effect = [
            # Multi-call step resets counter
            _llm_response(content="", tool_calls=[tc1, tc2], cost=0.001),
            _llm_response(content="done", cost=0.001),
        ]

        react = ReactExecutor(
            llm=mock_llm, executor=mock_executor, tool_schemas=[], max_iterations=10,
        )
        result = await react.execute("sys", "multi")

        assert result.trace.terminated_reason == "final_answer"


class TestBackwardCompatibility:
    @pytest.mark.asyncio
    async def test_engine_without_react(self):
        """LangGraphTaskEngine works without react_executor (legacy path)."""
        from infrastructure.task_graph.engine import LangGraphTaskEngine

        mock_llm = AsyncMock()
        mock_analyzer = AsyncMock()
        engine = LangGraphTaskEngine(llm=mock_llm, analyzer=mock_analyzer, react_executor=None)
        # Just verify construction works — no react_executor
        assert engine._react is None

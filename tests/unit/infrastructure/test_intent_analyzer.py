"""Tests for IntentAnalyzer — LLM-powered goal decomposition."""

import json
from unittest.mock import AsyncMock

import pytest

from domain.ports.llm_gateway import LLMGateway, LLMResponse
from infrastructure.task_graph.intent_analyzer import IntentAnalyzer


def _llm_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="ollama/qwen3:8b",
        prompt_tokens=50,
        completion_tokens=30,
        cost_usd=0.0,
    )


@pytest.fixture
def llm() -> AsyncMock:
    return AsyncMock(spec=LLMGateway)


@pytest.fixture
def analyzer(llm: AsyncMock) -> IntentAnalyzer:
    return IntentAnalyzer(llm)


class TestDecompose:
    async def test_decomposes_goal_into_subtasks(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Write fibonacci function", "deps": []},
                    {"description": "Write unit tests", "deps": [0]},
                ]
            )
        )
        # Use a goal that classifies as MEDIUM/COMPLEX to trigger LLM path
        subtasks = await analyzer.decompose(
            "Create a REST API endpoint with comprehensive tests"
        )

        assert len(subtasks) == 2
        assert subtasks[0].description == "Write fibonacci function"
        assert subtasks[1].description == "Write unit tests"

    async def test_resolves_index_dependencies_to_ids(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Step A", "deps": []},
                    {"description": "Step B", "deps": [0]},
                    {"description": "Step C", "deps": [0, 1]},
                ]
            )
        )
        subtasks = await analyzer.decompose(
            "Build a system with authentication, database, and testing"
        )

        assert subtasks[1].dependencies == [subtasks[0].id]
        assert subtasks[2].dependencies == [subtasks[0].id, subtasks[1].id]

    async def test_no_dependencies(self, analyzer: IntentAnalyzer, llm: AsyncMock) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Independent A", "deps": []},
                    {"description": "Independent B", "deps": []},
                ]
            )
        )
        subtasks = await analyzer.decompose(
            "Build frontend components and backend API endpoints together"
        )

        assert subtasks[0].dependencies == []
        assert subtasks[1].dependencies == []

    async def test_invalid_json_raises(self, analyzer: IntentAnalyzer, llm: AsyncMock) -> None:
        llm.complete.return_value = _llm_response("not valid json")

        with pytest.raises(json.JSONDecodeError):
            # Use complex goal to trigger LLM path
            await analyzer.decompose(
                "Build API with auth, database, and testing infrastructure"
            )

    async def test_uses_low_temperature(self, analyzer: IntentAnalyzer, llm: AsyncMock) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps([{"description": "Step 1", "deps": []}])
        )
        await analyzer.decompose(
            "Create a REST API with database integration"
        )

        call_kwargs = llm.complete.call_args[1]
        assert call_kwargs["temperature"] == 0.3

    async def test_ignores_invalid_dep_indices(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Step A", "deps": [99]},
                ]
            )
        )
        subtasks = await analyzer.decompose(
            "Build a frontend UI and backend server together"
        )

        assert subtasks[0].dependencies == []


class TestSimpleGoalSkipsLLM:
    """Sprint 9.1: SIMPLE goals should produce 1 subtask without LLM call."""

    async def test_simple_goal_returns_single_subtask(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        subtasks = await analyzer.decompose("FizzBuzz")

        assert len(subtasks) == 1
        assert subtasks[0].description == "FizzBuzz"

    async def test_simple_goal_does_not_call_llm(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        await analyzer.decompose("FizzBuzz")

        llm.complete.assert_not_called()

    async def test_fibonacci_is_simple(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        subtasks = await analyzer.decompose("Implement fibonacci in Python")

        assert len(subtasks) == 1
        assert subtasks[0].description == "Implement fibonacci in Python"
        llm.complete.assert_not_called()

    async def test_fix_bug_is_simple(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        subtasks = await analyzer.decompose("Fix the login bug")

        assert len(subtasks) == 1
        llm.complete.assert_not_called()

    async def test_simple_japanese(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        subtasks = await analyzer.decompose("FizzBuzzを書いて")

        assert len(subtasks) == 1
        assert subtasks[0].description == "FizzBuzzを書いて"
        llm.complete.assert_not_called()

    async def test_explain_is_simple(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        subtasks = await analyzer.decompose("Explain how quicksort works")

        assert len(subtasks) == 1
        llm.complete.assert_not_called()


class TestComplexityAwarePrompt:
    """Sprint 9.1: MEDIUM/COMPLEX goals use complexity-aware LLM prompt."""

    async def test_medium_goal_calls_llm(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Create API endpoint", "deps": []},
                    {"description": "Write tests", "deps": [0]},
                ]
            )
        )
        subtasks = await analyzer.decompose(
            "Create a REST API endpoint with unit tests"
        )

        assert len(subtasks) == 2
        llm.complete.assert_called_once()

    async def test_medium_prompt_contains_guidance(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps([{"description": "Step 1", "deps": []}])
        )
        await analyzer.decompose(
            "Create a REST API endpoint with database integration"
        )

        call_args = llm.complete.call_args[0][0]
        system_msg = call_args[0]["content"]
        assert "2-3 subtasks" in system_msg

    async def test_complex_prompt_contains_guidance(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps([{"description": "Step 1", "deps": []}])
        )
        await analyzer.decompose(
            "Build REST API with authentication, database, and testing"
        )

        call_args = llm.complete.call_args[0][0]
        system_msg = call_args[0]["content"]
        assert "3-5 subtasks" in system_msg

    async def test_prompt_requires_action_oriented(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps([{"description": "Step 1", "deps": []}])
        )
        await analyzer.decompose(
            "Create a REST API with database integration"
        )

        call_args = llm.complete.call_args[0][0]
        system_msg = call_args[0]["content"]
        assert "action-oriented" in system_msg


class TestExtractJson:
    """JSON extraction from various LLM output formats."""

    def test_plain_json(self) -> None:
        result = IntentAnalyzer._extract_json('[{"description": "x", "deps": []}]')
        assert json.loads(result)[0]["description"] == "x"

    def test_markdown_code_block(self) -> None:
        text = '```json\n[{"description": "x", "deps": []}]\n```'
        result = IntentAnalyzer._extract_json(text)
        assert json.loads(result)[0]["description"] == "x"

    def test_think_tags_stripped(self) -> None:
        text = '<think>reasoning</think>\n[{"description": "x", "deps": []}]'
        result = IntentAnalyzer._extract_json(text)
        assert json.loads(result)[0]["description"] == "x"

    def test_surrounding_text(self) -> None:
        text = 'Here is the plan:\n[{"description": "x", "deps": []}]\nDone.'
        result = IntentAnalyzer._extract_json(text)
        assert json.loads(result)[0]["description"] == "x"

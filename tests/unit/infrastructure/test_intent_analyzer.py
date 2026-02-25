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
            json.dumps([
                {"description": "Write fibonacci function", "deps": []},
                {"description": "Write unit tests", "deps": [0]},
            ])
        )
        subtasks = await analyzer.decompose("Implement fibonacci in Python")

        assert len(subtasks) == 2
        assert subtasks[0].description == "Write fibonacci function"
        assert subtasks[1].description == "Write unit tests"

    async def test_resolves_index_dependencies_to_ids(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps([
                {"description": "Step A", "deps": []},
                {"description": "Step B", "deps": [0]},
                {"description": "Step C", "deps": [0, 1]},
            ])
        )
        subtasks = await analyzer.decompose("Multi-step task")

        assert subtasks[1].dependencies == [subtasks[0].id]
        assert subtasks[2].dependencies == [subtasks[0].id, subtasks[1].id]

    async def test_no_dependencies(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps([
                {"description": "Independent A", "deps": []},
                {"description": "Independent B", "deps": []},
            ])
        )
        subtasks = await analyzer.decompose("Two independent tasks")

        assert subtasks[0].dependencies == []
        assert subtasks[1].dependencies == []

    async def test_invalid_json_raises(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response("not valid json")

        with pytest.raises(json.JSONDecodeError):
            await analyzer.decompose("Bad input")

    async def test_uses_low_temperature(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps([{"description": "Step 1", "deps": []}])
        )
        await analyzer.decompose("Test")

        call_kwargs = llm.complete.call_args[1]
        assert call_kwargs["temperature"] == 0.3

    async def test_ignores_invalid_dep_indices(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps([
                {"description": "Step A", "deps": [99]},
            ])
        )
        subtasks = await analyzer.decompose("Invalid deps")

        assert subtasks[0].dependencies == []

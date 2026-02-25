"""Tests for LangGraphTaskEngine — DAG execution with parallel + retry."""

from unittest.mock import AsyncMock

import pytest

from domain.entities.task import SubTask, TaskEntity
from domain.ports.llm_gateway import LLMGateway, LLMResponse
from domain.value_objects.status import SubTaskStatus
from infrastructure.task_graph.engine import LangGraphTaskEngine
from infrastructure.task_graph.intent_analyzer import IntentAnalyzer


def _ok_response(content: str = "result", cost: float = 0.0) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="ollama/qwen3:8b",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=cost,
    )


@pytest.fixture
def llm() -> AsyncMock:
    return AsyncMock(spec=LLMGateway)


@pytest.fixture
def analyzer() -> AsyncMock:
    return AsyncMock(spec=IntentAnalyzer)


@pytest.fixture
def engine(llm: AsyncMock, analyzer: AsyncMock) -> LangGraphTaskEngine:
    return LangGraphTaskEngine(llm, analyzer)


class TestExecute:
    async def test_single_subtask_success(
        self, engine: LangGraphTaskEngine, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _ok_response("fibonacci done")
        task = TaskEntity(
            goal="Implement fibonacci",
            subtasks=[SubTask(description="Write code")],
        )

        result = await engine.execute(task)

        assert result.subtasks[0].status == SubTaskStatus.SUCCESS
        assert result.subtasks[0].result == "fibonacci done"
        assert result.subtasks[0].model_used == "ollama/qwen3:8b"

    async def test_parallel_independent_subtasks(
        self, engine: LangGraphTaskEngine, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _ok_response("done")
        s1 = SubTask(description="Task A")
        s2 = SubTask(description="Task B")
        task = TaskEntity(goal="Parallel test", subtasks=[s1, s2])

        result = await engine.execute(task)

        assert result.subtasks[0].status == SubTaskStatus.SUCCESS
        assert result.subtasks[1].status == SubTaskStatus.SUCCESS
        # Both called in same batch → parallel via asyncio.gather
        assert llm.complete.await_count == 2

    async def test_sequential_dependent_subtasks(
        self, engine: LangGraphTaskEngine, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _ok_response("done")
        s1 = SubTask(description="Build foundation")
        s2 = SubTask(description="Build on top", dependencies=[s1.id])
        task = TaskEntity(goal="Sequential test", subtasks=[s1, s2])

        result = await engine.execute(task)

        assert result.subtasks[0].status == SubTaskStatus.SUCCESS
        assert result.subtasks[1].status == SubTaskStatus.SUCCESS
        # s1 in first batch, s2 in second → 2 LLM calls across 2 iterations
        assert llm.complete.await_count == 2

    async def test_retry_on_failure(
        self, engine: LangGraphTaskEngine, llm: AsyncMock
    ) -> None:
        llm.complete.side_effect = [
            Exception("Ollama timeout"),
            _ok_response("recovered"),
        ]
        task = TaskEntity(
            goal="Retry test",
            subtasks=[SubTask(description="Flaky task")],
        )

        result = await engine.execute(task)

        assert result.subtasks[0].status == SubTaskStatus.SUCCESS
        assert result.subtasks[0].result == "recovered"
        assert llm.complete.await_count == 2

    async def test_max_retries_marks_failed(
        self, engine: LangGraphTaskEngine, llm: AsyncMock
    ) -> None:
        llm.complete.side_effect = [
            Exception("fail 1"),
            Exception("fail 2"),
        ]
        task = TaskEntity(
            goal="Fail test",
            subtasks=[SubTask(description="Always fails")],
        )

        result = await engine.execute(task)

        assert result.subtasks[0].status == SubTaskStatus.FAILED
        assert "fail 2" in (result.subtasks[0].error or "")
        assert llm.complete.await_count == 2

    async def test_cascading_failure_blocks_dependents(
        self, engine: LangGraphTaskEngine, llm: AsyncMock
    ) -> None:
        llm.complete.side_effect = [
            Exception("fail 1"),
            Exception("fail 2"),
        ]
        s1 = SubTask(description="Foundation")
        s2 = SubTask(description="Dependent", dependencies=[s1.id])
        task = TaskEntity(goal="Cascade test", subtasks=[s1, s2])

        result = await engine.execute(task)

        assert result.subtasks[0].status == SubTaskStatus.FAILED
        assert result.subtasks[1].status == SubTaskStatus.FAILED
        assert "Blocked" in (result.subtasks[1].error or "")

    async def test_empty_task_completes_immediately(
        self, engine: LangGraphTaskEngine, llm: AsyncMock
    ) -> None:
        task = TaskEntity(goal="Empty task", subtasks=[])

        result = await engine.execute(task)

        llm.complete.assert_not_awaited()

    async def test_accumulates_cost(
        self, engine: LangGraphTaskEngine, llm: AsyncMock
    ) -> None:
        llm.complete.side_effect = [
            _ok_response("a", cost=0.01),
            _ok_response("b", cost=0.02),
        ]
        s1 = SubTask(description="Task A")
        s2 = SubTask(description="Task B")
        task = TaskEntity(goal="Cost test", subtasks=[s1, s2])

        result = await engine.execute(task)

        assert result.total_cost_usd == pytest.approx(0.03)


class TestDecompose:
    async def test_delegates_to_analyzer(
        self, engine: LangGraphTaskEngine, analyzer: AsyncMock
    ) -> None:
        expected = [SubTask(description="Step 1")]
        analyzer.decompose.return_value = expected

        result = await engine.decompose("Test goal")

        assert result == expected
        analyzer.decompose.assert_awaited_once_with("Test goal")

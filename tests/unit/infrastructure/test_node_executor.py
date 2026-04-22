"""Tests for NodeExecutor — PlanNode ↔ SubTask/TaskEntity bridge.

Sprint 15.5: ~10 tests covering conversion, artifact injection,
result application, and error handling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from domain.entities.fractal_engine import PlanNode
from domain.entities.task import SubTask, TaskEntity
from domain.ports.task_engine import TaskEngine
from domain.value_objects.status import SubTaskStatus, TaskStatus
from infrastructure.fractal.node_executor import NodeExecutor

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def inner_engine() -> AsyncMock:
    return AsyncMock(spec=TaskEngine)


@pytest.fixture
def executor(inner_engine: AsyncMock) -> NodeExecutor:
    return NodeExecutor(inner_engine)


def _node(
    desc: str = "Test step",
    *,
    is_terminal: bool = True,
    nesting: int = 0,
    input_artifacts: dict[str, str] | None = None,
    output_artifacts: dict[str, str] | None = None,
) -> PlanNode:
    return PlanNode(
        description=desc,
        is_terminal=is_terminal,
        nesting_level=nesting,
        input_artifacts=input_artifacts or {},
        output_artifacts=output_artifacts or {},
    )


def _success_task(
    subtask_id: str,
    result: str = "done",
    model: str = "test-model",
    cost: float = 0.01,
    engine: str | None = None,
    output_artifacts: dict[str, str] | None = None,
) -> TaskEntity:
    st = SubTask(
        id=subtask_id,
        description="x",
        status=SubTaskStatus.SUCCESS,
        result=result,
        model_used=model,
        cost_usd=cost,
        engine_used=engine,
        output_artifacts=output_artifacts or {},
    )
    return TaskEntity(goal="g", status=TaskStatus.SUCCESS, subtasks=[st])


def _failed_task(subtask_id: str, error: str = "oops") -> TaskEntity:
    st = SubTask(
        id=subtask_id,
        description="x",
        status=SubTaskStatus.FAILED,
        error=error,
    )
    return TaskEntity(goal="g", status=TaskStatus.FAILED, subtasks=[st])


# ---------------------------------------------------------------------------
# to_subtask
# ---------------------------------------------------------------------------


class TestToSubtask:
    def test_basic_conversion(self) -> None:
        node = _node("Do something")
        st = NodeExecutor.to_subtask(node)
        assert st.id == node.id
        assert st.description == "Do something"
        assert st.status == SubTaskStatus.PENDING

    def test_artifacts_copied(self) -> None:
        node = _node(input_artifacts={"key": "val"}, output_artifacts={"out": "data"})
        st = NodeExecutor.to_subtask(node)
        assert st.input_artifacts == {"key": "val"}
        assert st.output_artifacts == {"out": "data"}

    def test_artifacts_are_independent_copies(self) -> None:
        node = _node(input_artifacts={"k": "v"})
        st = NodeExecutor.to_subtask(node)
        st.input_artifacts["new"] = "added"
        assert "new" not in node.input_artifacts


# ---------------------------------------------------------------------------
# inject_artifacts
# ---------------------------------------------------------------------------


class TestInjectArtifacts:
    def test_injects_from_completed(self) -> None:
        prev = _node(output_artifacts={"data": "result123"})
        prev.status = SubTaskStatus.SUCCESS
        current = _node()
        NodeExecutor.inject_artifacts(current, [prev])
        assert current.input_artifacts == {"data": "result123"}

    def test_skips_non_success_nodes(self) -> None:
        prev = _node(output_artifacts={"data": "result123"})
        prev.status = SubTaskStatus.FAILED
        current = _node()
        NodeExecutor.inject_artifacts(current, [prev])
        assert current.input_artifacts == {}

    def test_does_not_overwrite_existing(self) -> None:
        prev = _node(output_artifacts={"key": "old"})
        prev.status = SubTaskStatus.SUCCESS
        current = _node(input_artifacts={"key": "existing"})
        NodeExecutor.inject_artifacts(current, [prev])
        assert current.input_artifacts["key"] == "existing"

    def test_merges_from_multiple_nodes(self) -> None:
        prev1 = _node(output_artifacts={"a": "1"})
        prev1.status = SubTaskStatus.SUCCESS
        prev2 = _node(output_artifacts={"b": "2"})
        prev2.status = SubTaskStatus.SUCCESS
        current = _node()
        NodeExecutor.inject_artifacts(current, [prev1, prev2])
        assert current.input_artifacts == {"a": "1", "b": "2"}


# ---------------------------------------------------------------------------
# execute_terminal
# ---------------------------------------------------------------------------


class TestExecuteTerminal:
    @pytest.mark.asyncio
    async def test_success_applies_result(
        self, executor: NodeExecutor, inner_engine: AsyncMock
    ) -> None:
        node = _node("Run task")
        inner_engine.execute.return_value = _success_task(node.id)
        await executor.execute_terminal(node, "parent goal")
        assert node.status == SubTaskStatus.SUCCESS
        assert node.result == "done"
        assert node.model_used == "test-model"
        assert node.cost_usd == 0.01

    @pytest.mark.asyncio
    async def test_failed_subtask_propagates(
        self, executor: NodeExecutor, inner_engine: AsyncMock
    ) -> None:
        node = _node("Failing task")
        inner_engine.execute.return_value = _failed_task(node.id, "network error")
        await executor.execute_terminal(node, "goal")
        assert node.status == SubTaskStatus.FAILED
        assert node.error == "network error"

    @pytest.mark.asyncio
    async def test_engine_exception_sets_failed(
        self, executor: NodeExecutor, inner_engine: AsyncMock
    ) -> None:
        node = _node("Bad task")
        inner_engine.execute.side_effect = RuntimeError("engine crash")
        await executor.execute_terminal(node, "goal")
        assert node.status == SubTaskStatus.FAILED
        assert "engine crash" in (node.error or "")

    @pytest.mark.asyncio
    async def test_empty_subtasks_sets_failed(
        self, executor: NodeExecutor, inner_engine: AsyncMock
    ) -> None:
        node = _node("Empty result")
        inner_engine.execute.return_value = TaskEntity(
            goal="g", status=TaskStatus.SUCCESS, subtasks=[]
        )
        await executor.execute_terminal(node, "goal")
        assert node.status == SubTaskStatus.FAILED
        assert "no subtasks" in (node.error or "").lower()

    @pytest.mark.asyncio
    async def test_engine_used_takes_precedence(
        self, executor: NodeExecutor, inner_engine: AsyncMock
    ) -> None:
        node = _node("Task with engine")
        inner_engine.execute.return_value = _success_task(node.id, engine="gemini-cli")
        await executor.execute_terminal(node, "goal")
        assert node.model_used == "gemini-cli"

    @pytest.mark.asyncio
    async def test_output_artifacts_merged(
        self, executor: NodeExecutor, inner_engine: AsyncMock
    ) -> None:
        node = _node("Generate output")
        inner_engine.execute.return_value = _success_task(
            node.id, output_artifacts={"code": "print('hi')"}
        )
        await executor.execute_terminal(node, "goal")
        assert node.output_artifacts == {"code": "print('hi')"}

    @pytest.mark.asyncio
    async def test_input_artifacts_included_in_description(
        self, executor: NodeExecutor, inner_engine: AsyncMock
    ) -> None:
        node = _node("Use context", input_artifacts={"prev": "data123"})
        inner_engine.execute.return_value = _success_task(node.id)
        await executor.execute_terminal(node, "goal")
        # Verify the task passed to inner engine includes artifact info
        call_args = inner_engine.execute.call_args
        task_arg: TaskEntity = call_args[0][0]
        assert "prev: data123" in task_arg.subtasks[0].description

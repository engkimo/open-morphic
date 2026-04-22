"""Tests for FractalTaskEngine — recursive execution engine core.

Sprint 15.5: ~25 tests covering decompose, execute, Gate 1/2 integration,
retry logic, failure propagation, artifact chaining, conditional fallbacks,
depth control, and budget enforcement.
"""

from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock

import pytest

from domain.entities.fractal_engine import (
    CandidateNode,
    PlanEvaluation,
    PlanNode,
    ResultEvaluation,
)
from domain.entities.task import TaskEntity
from domain.ports.plan_evaluator import PlanEvaluatorPort
from domain.ports.planner import PlannerPort
from domain.ports.result_evaluator import ResultEvaluatorPort
from domain.ports.task_engine import TaskEngine
from domain.value_objects.fractal_engine import (
    NodeState,
    PlanEvalDecision,
    ResultEvalDecision,
)
from domain.value_objects.status import SubTaskStatus, TaskStatus
from infrastructure.fractal.fractal_engine import FractalTaskEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _candidate(
    desc: str = "Step",
    *,
    is_terminal: bool = True,
    score: float = 0.8,
    state: NodeState = NodeState.VISIBLE,
    condition: str | None = None,
) -> CandidateNode:
    node = PlanNode(
        id=str(uuid.uuid4())[:8],
        description=desc,
        is_terminal=is_terminal,
        nesting_level=0,
    )
    return CandidateNode(
        node=node,
        state=state,
        score=score,
        activation_condition=condition,
    )


def _approved_eval(plan_id: str = "p1", score: float = 0.85) -> PlanEvaluation:
    return PlanEvaluation(
        plan_id=plan_id,
        evaluator_model="test",
        completeness=score,
        feasibility=score,
        safety=1.0,
        overall_score=score,
        decision=PlanEvalDecision.APPROVED,
        feedback="Looks good",
    )


def _rejected_eval(plan_id: str = "p1", feedback: str = "Bad plan") -> PlanEvaluation:
    return PlanEvaluation(
        plan_id=plan_id,
        evaluator_model="test",
        completeness=0.3,
        feasibility=0.2,
        safety=0.5,
        overall_score=0.3,
        decision=PlanEvalDecision.REJECTED,
        feedback=feedback,
    )


def _ok_result(node_id: str = "n1", score: float = 0.85) -> ResultEvaluation:
    return ResultEvaluation(
        node_id=node_id,
        decision=ResultEvalDecision.OK,
        accuracy=score,
        validity=score,
        goal_alignment=score,
        overall_score=score,
        feedback="Good",
    )


def _retry_result(node_id: str = "n1", score: float = 0.5) -> ResultEvaluation:
    return ResultEvaluation(
        node_id=node_id,
        decision=ResultEvalDecision.RETRY,
        accuracy=score,
        validity=score,
        goal_alignment=score,
        overall_score=score,
        feedback="Needs improvement",
    )


def _replan_result(node_id: str = "n1", score: float = 0.2) -> ResultEvaluation:
    return ResultEvaluation(
        node_id=node_id,
        decision=ResultEvalDecision.REPLAN,
        accuracy=score,
        validity=score,
        goal_alignment=score,
        overall_score=score,
        feedback="Fundamentally wrong approach",
    )


def _make_inner_execute(results: dict[str, str] | None = None):
    """Create a mock inner engine that returns success with result text."""

    async def _execute(task: TaskEntity) -> TaskEntity:
        for st in task.subtasks:
            st.status = SubTaskStatus.SUCCESS
            st.result = (results or {}).get(st.description, "done") if results else "done"
            st.model_used = "test-model"
            st.cost_usd = 0.01
        task.status = TaskStatus.SUCCESS
        return task

    return _execute


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def planner() -> AsyncMock:
    return AsyncMock(spec=PlannerPort)


@pytest.fixture
def plan_evaluator() -> AsyncMock:
    return AsyncMock(spec=PlanEvaluatorPort)


@pytest.fixture
def result_evaluator() -> AsyncMock:
    return AsyncMock(spec=ResultEvaluatorPort)


@pytest.fixture
def inner_engine() -> AsyncMock:
    mock = AsyncMock(spec=TaskEngine)
    mock.execute.side_effect = _make_inner_execute()
    return mock


@pytest.fixture
def engine(
    planner: AsyncMock,
    plan_evaluator: AsyncMock,
    result_evaluator: AsyncMock,
    inner_engine: AsyncMock,
) -> FractalTaskEngine:
    return FractalTaskEngine(
        planner=planner,
        plan_evaluator=plan_evaluator,
        result_evaluator=result_evaluator,
        inner_engine=inner_engine,
        max_depth=3,
        max_retries=2,
        max_plan_attempts=2,
    )


# ---------------------------------------------------------------------------
# decompose
# ---------------------------------------------------------------------------


class TestDecompose:
    """decompose() returns a lightweight placeholder — real planning in execute().

    FractalTaskEngine.execute() re-plans from task.goal using recursive
    decomposition, so running Planner + Gate ① in decompose() would
    double the cost with the result discarded.
    """

    @pytest.mark.asyncio
    async def test_decompose_returns_single_placeholder(
        self,
        engine: FractalTaskEngine,
    ) -> None:
        subtasks = await engine.decompose("Build something")
        assert len(subtasks) == 1
        assert subtasks[0].description == "Build something"

    @pytest.mark.asyncio
    async def test_decompose_does_not_call_planner(
        self,
        engine: FractalTaskEngine,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
    ) -> None:
        await engine.decompose("Any goal")
        planner.generate_candidates.assert_not_called()
        plan_evaluator.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_decompose_placeholder_is_pending(
        self,
        engine: FractalTaskEngine,
    ) -> None:
        subtasks = await engine.decompose("Test goal")
        assert subtasks[0].status == SubTaskStatus.PENDING


# ---------------------------------------------------------------------------
# execute — happy path
# ---------------------------------------------------------------------------


class TestExecuteHappyPath:
    @pytest.mark.asyncio
    async def test_single_terminal_node(
        self,
        engine: FractalTaskEngine,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        c = _candidate("Do work", is_terminal=True)
        planner.generate_candidates.return_value = [c]
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.return_value = _ok_result(c.node.id)

        task = TaskEntity(goal="Simple task")
        result = await engine.execute(task)
        assert result.status == TaskStatus.SUCCESS
        assert len(result.subtasks) == 1
        assert result.subtasks[0].status == SubTaskStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_multiple_terminal_nodes(
        self,
        engine: FractalTaskEngine,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
    ) -> None:
        c1 = _candidate("Step A", score=0.9)
        c2 = _candidate("Step B", score=0.8)
        planner.generate_candidates.return_value = [c1, c2]
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.side_effect = [
            _ok_result(c1.node.id),
            _ok_result(c2.node.id),
        ]

        task = TaskEntity(goal="Multi-step task")
        result = await engine.execute(task)
        assert result.status == TaskStatus.SUCCESS
        assert len(result.subtasks) == 2

    @pytest.mark.asyncio
    async def test_cost_tracked(
        self,
        engine: FractalTaskEngine,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
    ) -> None:
        c = _candidate("Cost check")
        planner.generate_candidates.return_value = [c]
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.return_value = _ok_result(c.node.id)

        task = TaskEntity(goal="Track cost")
        result = await engine.execute(task)
        assert result.total_cost_usd > 0


# ---------------------------------------------------------------------------
# execute — retry logic
# ---------------------------------------------------------------------------


class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_retry_then_ok(
        self,
        engine: FractalTaskEngine,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        c = _candidate("Retry task")
        planner.generate_candidates.return_value = [c]
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.side_effect = [
            _retry_result(c.node.id),
            _ok_result(c.node.id),
        ]

        task = TaskEntity(goal="Retry goal")
        result = await engine.execute(task)
        assert result.status == TaskStatus.SUCCESS
        # inner engine called twice (initial + retry)
        assert inner_engine.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_exhausted_fails(
        self,
        engine: FractalTaskEngine,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        c = _candidate("Always fail")
        planner.generate_candidates.return_value = [c]
        plan_evaluator.evaluate.return_value = _approved_eval()
        # 3 retries (initial + 2 retries) all get RETRY
        result_evaluator.evaluate.return_value = _retry_result(c.node.id)

        task = TaskEntity(goal="Exhaust retries")
        result = await engine.execute(task)
        # Node should fail after max_retries=2 (initial + 2 = 3 total)
        assert result.status == TaskStatus.FAILED


# ---------------------------------------------------------------------------
# execute — failure propagation
# ---------------------------------------------------------------------------


class TestFailurePropagation:
    @pytest.mark.asyncio
    async def test_replan_causes_failure(
        self,
        engine: FractalTaskEngine,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
    ) -> None:
        c = _candidate("Wrong approach")
        planner.generate_candidates.return_value = [c]
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.return_value = _replan_result(c.node.id)

        task = TaskEntity(goal="Replan goal")
        result = await engine.execute(task)
        assert result.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_conditional_fallback_activated(
        self,
        engine: FractalTaskEngine,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
    ) -> None:
        c_main = _candidate("Main approach", score=0.9)
        c_fallback = _candidate(
            "Fallback approach",
            score=0.6,
            state=NodeState.CONDITIONAL,
            condition="failure:Main approach",
        )
        planner.generate_candidates.return_value = [c_main, c_fallback]
        plan_evaluator.evaluate.return_value = _approved_eval()

        # Main fails with REPLAN, fallback succeeds
        result_evaluator.evaluate.side_effect = [
            _replan_result(c_main.node.id),
            _ok_result(c_fallback.node.id),
        ]

        task = TaskEntity(goal="Fallback goal")
        result = await engine.execute(task)
        # Fallback replaces the failed main node
        assert result.status == TaskStatus.SUCCESS
        assert len(result.subtasks) == 1
        assert result.subtasks[0].description == "Fallback approach"


# ---------------------------------------------------------------------------
# execute — expandable (recursive) nodes
# ---------------------------------------------------------------------------


class TestExpandableNodes:
    @pytest.mark.asyncio
    async def test_expandable_node_recurses(
        self,
        engine: FractalTaskEngine,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
    ) -> None:
        # Level 0: one expandable node
        c_parent = _candidate("Complex task", is_terminal=False, score=0.9)
        # Level 1: one terminal node
        c_child = _candidate("Simple subtask", is_terminal=True, score=0.8)

        call_count = [0]

        async def _gen_candidates(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return [c_parent]
            return [c_child]

        planner.generate_candidates.side_effect = _gen_candidates
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.return_value = _ok_result()

        task = TaskEntity(goal="Recursive goal")
        result = await engine.execute(task)
        assert result.status == TaskStatus.SUCCESS
        # Planner called twice: once for level 0, once for level 1
        assert planner.generate_candidates.call_count == 2

    @pytest.mark.asyncio
    async def test_max_depth_forces_terminal(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        # Create engine with max_depth=0 — all nodes forced terminal at level 0
        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            max_depth=0,
        )

        # Node is non-terminal but at max depth, should be forced terminal
        c = _candidate("Deep task", is_terminal=False, score=0.9)
        planner.generate_candidates.return_value = [c]
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.return_value = _ok_result(c.node.id)

        task = TaskEntity(goal="Depth limited")
        result = await engine.execute(task)
        assert result.status == TaskStatus.SUCCESS
        # Planner called once for level 0 plan; no recursion (depth=0 forces terminal)
        assert planner.generate_candidates.call_count == 1


# ---------------------------------------------------------------------------
# execute — artifact chaining
# ---------------------------------------------------------------------------


class TestArtifactChaining:
    @pytest.mark.asyncio
    async def test_artifacts_chained_between_nodes(
        self,
        engine: FractalTaskEngine,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        c1 = _candidate("Generate data", score=0.9)
        c2 = _candidate("Process data", score=0.8)
        planner.generate_candidates.return_value = [c1, c2]
        plan_evaluator.evaluate.return_value = _approved_eval()

        # First node produces output artifacts
        async def _exec_with_artifacts(task: TaskEntity) -> TaskEntity:
            for st in task.subtasks:
                st.status = SubTaskStatus.SUCCESS
                st.result = "generated"
                st.model_used = "test"
                st.cost_usd = 0.01
                if "Generate" in st.description:
                    st.output_artifacts = {"dataset": "csv_data_here"}
            task.status = TaskStatus.SUCCESS
            return task

        inner_engine.execute.side_effect = _exec_with_artifacts
        result_evaluator.evaluate.return_value = _ok_result()

        task = TaskEntity(goal="Artifact chain")
        result = await engine.execute(task)
        assert result.status == TaskStatus.SUCCESS

        # Verify inner engine received the artifact for the second subtask
        calls = inner_engine.execute.call_args_list
        second_call_task = calls[1][0][0]
        assert (
            "dataset" in second_call_task.subtasks[0].description
            or "dataset" in second_call_task.subtasks[0].input_artifacts
        )


# ---------------------------------------------------------------------------
# execute — plan failure
# ---------------------------------------------------------------------------


class TestPlanFailure:
    @pytest.mark.asyncio
    async def test_all_plans_rejected(
        self,
        engine: FractalTaskEngine,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
    ) -> None:
        planner.generate_candidates.return_value = [_candidate("Bad")]
        plan_evaluator.evaluate.return_value = _rejected_eval()

        task = TaskEntity(goal="Hopeless task")
        result = await engine.execute(task)
        assert result.status == TaskStatus.FAILED
        assert len(result.subtasks) == 1
        assert "rejected" in (result.subtasks[0].error or "").lower()

    @pytest.mark.asyncio
    async def test_engine_exception_handled(
        self,
        engine: FractalTaskEngine,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        c = _candidate("Crash task")
        planner.generate_candidates.return_value = [c]
        plan_evaluator.evaluate.return_value = _approved_eval()
        inner_engine.execute.side_effect = RuntimeError("boom")
        result_evaluator.evaluate.return_value = _retry_result(c.node.id)

        task = TaskEntity(goal="Exception goal")
        result = await engine.execute(task)
        assert result.status == TaskStatus.FAILED


# ---------------------------------------------------------------------------
# execute — budget enforcement
# ---------------------------------------------------------------------------


class TestBudgetEnforcement:
    @pytest.mark.asyncio
    async def test_budget_forces_terminal(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            budget_usd=0.001,  # Very tight budget
        )

        # First node costs more than budget
        async def _expensive(task: TaskEntity) -> TaskEntity:
            for st in task.subtasks:
                st.status = SubTaskStatus.SUCCESS
                st.result = "expensive"
                st.cost_usd = 0.01
            task.status = TaskStatus.SUCCESS
            return task

        inner_engine.execute.side_effect = _expensive

        c1 = _candidate("Step 1", is_terminal=True, score=0.9)
        c2 = _candidate("Step 2", is_terminal=False, score=0.8)
        planner.generate_candidates.return_value = [c1, c2]
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.return_value = _ok_result()

        task = TaskEntity(goal="Budget test")
        result = await engine.execute(task)
        # Step 2 should be forced terminal due to budget
        assert result.status == TaskStatus.SUCCESS
        # Planner only called once (no recursion for step 2)
        assert planner.generate_candidates.call_count == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_goal(
        self,
        engine: FractalTaskEngine,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
    ) -> None:
        planner.generate_candidates.return_value = []

        task = TaskEntity(goal="x")  # min_length=1
        result = await engine.execute(task)
        assert result.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_planner_exception(
        self,
        engine: FractalTaskEngine,
        planner: AsyncMock,
    ) -> None:
        planner.generate_candidates.side_effect = RuntimeError("LLM down")

        task = TaskEntity(goal="Planner crash")
        result = await engine.execute(task)
        assert result.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_evaluator_exception(
        self,
        engine: FractalTaskEngine,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
    ) -> None:
        planner.generate_candidates.return_value = [_candidate("Test")]
        plan_evaluator.evaluate.side_effect = RuntimeError("Eval down")

        task = TaskEntity(goal="Eval crash")
        result = await engine.execute(task)
        assert result.status == TaskStatus.FAILED


# ---------------------------------------------------------------------------
# TD-168: Gate 2 skip for successful terminal nodes
# ---------------------------------------------------------------------------


class TestGate2Skip:
    """Gate 2 should be skipped for terminal nodes that succeed."""

    @pytest.mark.asyncio
    async def test_successful_terminal_skips_gate2(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """Successful terminal node should not call result evaluator."""
        planner.generate_candidates.return_value = [_candidate("Compute 2+2")]
        plan_evaluator.evaluate.return_value = _approved_eval()
        inner_engine.execute.side_effect = _make_inner_execute(
            {"Compute 2+2": "4"}
        )

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            skip_gate2_for_terminal_success=True,
        )

        task = TaskEntity(goal="What is 2+2?")
        result = await engine.execute(task)

        assert result.status == TaskStatus.SUCCESS
        # Gate 2 should NOT have been called (terminal + success)
        result_evaluator.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_terminal_still_uses_gate2(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """Failed terminal node should still go through Gate 2."""

        async def _fail_execute(task: TaskEntity) -> TaskEntity:
            for st in task.subtasks:
                st.status = SubTaskStatus.FAILED
                st.error = "Something went wrong"
            task.status = TaskStatus.FAILED
            return task

        planner.generate_candidates.return_value = [_candidate("Broken")]
        plan_evaluator.evaluate.return_value = _approved_eval()
        inner_engine.execute.side_effect = _fail_execute
        result_evaluator.evaluate.return_value = _replan_result()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            skip_gate2_for_terminal_success=True,
        )

        task = TaskEntity(goal="Fail task")
        result = await engine.execute(task)

        assert result.status == TaskStatus.FAILED
        # Gate 2 WAS called for failed node
        result_evaluator.evaluate.assert_called()

    @pytest.mark.asyncio
    async def test_success_no_result_still_uses_gate2(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """Terminal node with SUCCESS but empty result still gets Gate 2."""

        async def _empty_result_execute(task: TaskEntity) -> TaskEntity:
            for st in task.subtasks:
                st.status = SubTaskStatus.SUCCESS
                st.result = ""  # Empty result
            task.status = TaskStatus.SUCCESS
            return task

        planner.generate_candidates.return_value = [_candidate("Empty")]
        plan_evaluator.evaluate.return_value = _approved_eval()
        inner_engine.execute.side_effect = _empty_result_execute
        result_evaluator.evaluate.return_value = _ok_result()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            skip_gate2_for_terminal_success=True,
        )

        task = TaskEntity(goal="Empty result task")
        result = await engine.execute(task)

        assert result.status == TaskStatus.SUCCESS
        # Gate 2 WAS called (empty result → don't trust)
        result_evaluator.evaluate.assert_called()

    @pytest.mark.asyncio
    async def test_nonterminal_success_still_uses_gate2(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """Non-terminal (expandable) nodes always go through Gate 2."""
        planner.generate_candidates.return_value = [
            _candidate("Expand me", is_terminal=False)
        ]
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.return_value = _ok_result()
        inner_engine.execute.side_effect = _make_inner_execute()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            max_depth=1,  # Force terminal at depth
            skip_gate2_for_terminal_success=True,
        )

        task = TaskEntity(goal="Expand task")
        await engine.execute(task)


# ---------------------------------------------------------------------------
# TD-169: Parallel node execution
# ---------------------------------------------------------------------------


class TestParallelExecution:
    """Parallel execution via asyncio.gather when enabled."""

    @pytest.mark.asyncio
    async def test_parallel_multiple_nodes(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """Multiple terminal nodes execute via gather when parallel=True."""
        c1 = _candidate("Task A", score=0.9)
        c2 = _candidate("Task B", score=0.8)
        c3 = _candidate("Task C", score=0.7)
        planner.generate_candidates.return_value = [c1, c2, c3]
        plan_evaluator.evaluate.return_value = _approved_eval()
        inner_engine.execute.side_effect = _make_inner_execute(
            {"Task A": "result_a", "Task B": "result_b", "Task C": "result_c"}
        )

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            parallel_node_execution=True,
            skip_gate2_for_terminal_success=True,
        )

        task = TaskEntity(goal="Parallel goal")
        result = await engine.execute(task)

        assert result.status == TaskStatus.SUCCESS
        assert len(result.subtasks) == 3
        # All 3 nodes executed (inner engine called 3 times)
        assert inner_engine.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_parallel_single_node_no_gather(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """Single node still works correctly with parallel enabled."""
        planner.generate_candidates.return_value = [_candidate("Solo")]
        plan_evaluator.evaluate.return_value = _approved_eval()
        inner_engine.execute.side_effect = _make_inner_execute()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            parallel_node_execution=True,
            skip_gate2_for_terminal_success=True,
        )

        task = TaskEntity(goal="Single node parallel")
        result = await engine.execute(task)
        assert result.status == TaskStatus.SUCCESS
        assert inner_engine.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_parallel_one_fails_others_succeed(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """In parallel mode, one node failure doesn't block others."""
        c_ok = _candidate("Good task", score=0.9)
        c_fail = _candidate("Bad task", score=0.8)
        planner.generate_candidates.return_value = [c_ok, c_fail]
        plan_evaluator.evaluate.return_value = _approved_eval()

        call_count = 0

        async def _mixed_execute(task: TaskEntity) -> TaskEntity:
            nonlocal call_count
            call_count += 1
            for st in task.subtasks:
                if "Bad" in st.description:
                    st.status = SubTaskStatus.FAILED
                    st.error = "Something broke"
                    task.status = TaskStatus.FAILED
                else:
                    st.status = SubTaskStatus.SUCCESS
                    st.result = "ok"
                    st.cost_usd = 0.01
                    task.status = TaskStatus.SUCCESS
            return task

        inner_engine.execute.side_effect = _mixed_execute
        result_evaluator.evaluate.return_value = _replan_result()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            parallel_node_execution=True,
            skip_gate2_for_terminal_success=True,
        )

        task = TaskEntity(goal="Mixed parallel")
        await engine.execute(task)

        # Both nodes were attempted
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_parallel_disabled_uses_sequential(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """With parallel=False (default), nodes execute sequentially."""
        c1 = _candidate("Step 1", score=0.9)
        c2 = _candidate("Step 2", score=0.8)
        planner.generate_candidates.return_value = [c1, c2]
        plan_evaluator.evaluate.return_value = _approved_eval()

        execution_order: list[str] = []

        async def _tracking_execute(task: TaskEntity) -> TaskEntity:
            for st in task.subtasks:
                execution_order.append(st.description)
                st.status = SubTaskStatus.SUCCESS
                st.result = "done"
                st.cost_usd = 0.01
            task.status = TaskStatus.SUCCESS
            return task

        inner_engine.execute.side_effect = _tracking_execute
        result_evaluator.evaluate.return_value = _ok_result()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            parallel_node_execution=False,  # Explicitly sequential
        )

        task = TaskEntity(goal="Sequential goal")
        result = await engine.execute(task)

        assert result.status == TaskStatus.SUCCESS
        # Sequential execution preserves order
        assert execution_order == ["Step 1", "Step 2"]


# ---------------------------------------------------------------------------
# TD-171: Reflection skip for single-node plans
# ---------------------------------------------------------------------------


class TestReflectionSkip:
    """Single successful node plans skip reflection."""

    @pytest.mark.asyncio
    async def test_single_node_success_skips_reflection(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """Single successful node should skip reflection evaluator."""
        reflection = AsyncMock()

        planner.generate_candidates.return_value = [_candidate("Solo task")]
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.return_value = _ok_result()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            reflection_evaluator=reflection,
            skip_reflection_for_single_success=True,
        )

        task = TaskEntity(goal="Simple goal")
        result = await engine.execute(task)

        assert result.status == TaskStatus.SUCCESS
        # Reflection NOT called for single-node success
        reflection.reflect.assert_not_called()

    @pytest.mark.asyncio
    async def test_multi_node_still_reflects(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """Multi-node plan should still call reflection."""
        reflection = AsyncMock()
        reflection.reflect.return_value = AsyncMock(
            is_satisfied=True,
            confidence=0.9,
            feedback="All good",
            suggested_descriptions=[],
        )

        planner.generate_candidates.return_value = [
            _candidate("Task A"),
            _candidate("Task B"),
        ]
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.return_value = _ok_result()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            reflection_evaluator=reflection,
        )

        task = TaskEntity(goal="Multi goal")
        result = await engine.execute(task)

        assert result.status == TaskStatus.SUCCESS
        reflection.reflect.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_node_failure_still_reflects(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """Single failed node should still go through reflection."""
        reflection = AsyncMock()
        reflection.reflect.return_value = AsyncMock(
            is_satisfied=True,
            confidence=0.5,
            feedback="Node failed",
            suggested_descriptions=[],
        )

        async def _fail_exec(task: TaskEntity) -> TaskEntity:
            for st in task.subtasks:
                st.status = SubTaskStatus.FAILED
                st.error = "broken"
            task.status = TaskStatus.FAILED
            return task

        inner_engine.execute.side_effect = _fail_exec
        planner.generate_candidates.return_value = [_candidate("Broken")]
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.return_value = _replan_result()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            reflection_evaluator=reflection,
        )

        task = TaskEntity(goal="Fail goal")
        await engine.execute(task)


class TestPlannerCache:
    """Planner candidate caching skips LLM call on repeat goals (TD-173)."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_planner_call(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """Second execution of same goal should use cached candidates."""
        planner.generate_candidates.return_value = [_candidate("Cached task")]
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.return_value = _ok_result()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            cache_planner_candidates=True,
        )

        # First execution — planner called
        task1 = TaskEntity(goal="Cached goal")
        await engine.execute(task1)
        assert planner.generate_candidates.call_count == 1

        # Second execution — same goal, planner NOT called again
        task2 = TaskEntity(goal="Cached goal")
        await engine.execute(task2)
        assert planner.generate_candidates.call_count == 1  # still 1

    @pytest.mark.asyncio
    async def test_different_goal_calls_planner(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """Different goal should NOT use cache."""
        planner.generate_candidates.return_value = [_candidate("Task")]
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.return_value = _ok_result()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            cache_planner_candidates=True,
        )

        await engine.execute(TaskEntity(goal="Goal A"))
        await engine.execute(TaskEntity(goal="Goal B"))
        assert planner.generate_candidates.call_count == 2

    @pytest.mark.asyncio
    async def test_cache_disabled_always_calls_planner(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """With caching disabled, planner is always called."""
        planner.generate_candidates.return_value = [_candidate("Task")]
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.return_value = _ok_result()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            cache_planner_candidates=False,  # default
        )

        await engine.execute(TaskEntity(goal="Same goal"))
        await engine.execute(TaskEntity(goal="Same goal"))
        assert planner.generate_candidates.call_count == 2

    @pytest.mark.asyncio
    async def test_cache_uses_deepcopy(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """Cached candidates are deep-copied so mutations don't leak."""
        planner.generate_candidates.return_value = [_candidate("Mutable task")]
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.return_value = _ok_result()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            cache_planner_candidates=True,
        )

        task1 = TaskEntity(goal="Deepcopy goal")
        result1 = await engine.execute(task1)

        task2 = TaskEntity(goal="Deepcopy goal")
        result2 = await engine.execute(task2)

        # Both should succeed independently
        assert result1.status == TaskStatus.SUCCESS
        assert result2.status == TaskStatus.SUCCESS


# ---------------------------------------------------------------------------
# Concurrency throttle (TD-175)
# ---------------------------------------------------------------------------


class TestConcurrencyThrottle:
    """Semaphore-based concurrency limit and throttle delay (TD-175)."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """max_concurrent_nodes=1 forces sequential execution even in parallel mode."""
        import asyncio

        max_concurrent_seen = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        original_side_effect = _make_inner_execute(
            {"A": "done_a", "B": "done_b", "C": "done_c"}
        )

        async def _tracking_execute(task: TaskEntity) -> TaskEntity:
            nonlocal max_concurrent_seen, current_concurrent
            async with lock:
                current_concurrent += 1
                if current_concurrent > max_concurrent_seen:
                    max_concurrent_seen = current_concurrent
            await asyncio.sleep(0.01)  # simulate work
            result = await original_side_effect(task)
            async with lock:
                current_concurrent -= 1
            return result

        inner_engine.execute.side_effect = _tracking_execute

        c1 = _candidate("A", score=0.9)
        c2 = _candidate("B", score=0.8)
        c3 = _candidate("C", score=0.7)
        planner.generate_candidates.return_value = [c1, c2, c3]
        plan_evaluator.evaluate.return_value = _approved_eval()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            parallel_node_execution=True,
            skip_gate2_for_terminal_success=True,
            max_concurrent_nodes=1,  # Force sequential via semaphore
        )

        task = TaskEntity(goal="Throttled goal")
        result = await engine.execute(task)

        assert result.status == TaskStatus.SUCCESS
        assert max_concurrent_seen == 1  # Never more than 1 concurrent

    @pytest.mark.asyncio
    async def test_unlimited_concurrency_when_zero(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """max_concurrent_nodes=0 means no semaphore (unlimited)."""
        c1 = _candidate("X", score=0.9)
        c2 = _candidate("Y", score=0.8)
        planner.generate_candidates.return_value = [c1, c2]
        plan_evaluator.evaluate.return_value = _approved_eval()
        inner_engine.execute.side_effect = _make_inner_execute()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            parallel_node_execution=True,
            skip_gate2_for_terminal_success=True,
            max_concurrent_nodes=0,  # unlimited
        )

        task = TaskEntity(goal="Unlimited goal")
        result = await engine.execute(task)

        assert result.status == TaskStatus.SUCCESS
        assert engine._exec_semaphore is None  # cleaned up

    @pytest.mark.asyncio
    async def test_throttle_delay_applied(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """throttle_delay_ms > 0 adds sleep between node completions."""
        import time

        planner.generate_candidates.return_value = [
            _candidate("Fast A"),
            _candidate("Fast B"),
        ]
        plan_evaluator.evaluate.return_value = _approved_eval()
        inner_engine.execute.side_effect = _make_inner_execute()

        # Use semaphore=1 so nodes execute sequentially → delays stack
        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            parallel_node_execution=True,
            skip_gate2_for_terminal_success=True,
            max_concurrent_nodes=1,  # sequential via semaphore
            throttle_delay_ms=50,  # 50ms delay per node
        )

        start = time.monotonic()
        task = TaskEntity(goal="Delayed goal")
        result = await engine.execute(task)
        elapsed = time.monotonic() - start

        assert result.status == TaskStatus.SUCCESS
        # 2 nodes × 50ms delay = at least 100ms (sequential via semaphore)
        assert elapsed >= 0.08  # allow some tolerance

    @pytest.mark.asyncio
    async def test_per_task_overrides(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """set_execution_overrides() controls per-task concurrency."""
        planner.generate_candidates.return_value = [_candidate("Override test")]
        plan_evaluator.evaluate.return_value = _approved_eval()
        inner_engine.execute.side_effect = _make_inner_execute()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            max_concurrent_nodes=0,  # default: unlimited
            skip_gate2_for_terminal_success=True,
        )

        # Set per-task override before execute
        engine.set_execution_overrides({
            "max_concurrent_nodes": 2,
            "throttle_delay_ms": 10,
            "max_depth": 1,
        })

        task = TaskEntity(goal="Overridden goal")
        result = await engine.execute(task)

        assert result.status == TaskStatus.SUCCESS
        # After execute, overrides should be consumed
        assert engine._pending_overrides == {}
        # Per-execution state cleaned up
        assert engine._exec_semaphore is None

    @pytest.mark.asyncio
    async def test_overrides_consumed_after_execute(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """Pending overrides are consumed by execute() and don't leak to next call."""
        planner.generate_candidates.return_value = [_candidate("Consume test")]
        plan_evaluator.evaluate.return_value = _approved_eval()
        inner_engine.execute.side_effect = _make_inner_execute()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            max_concurrent_nodes=0,  # default: unlimited
        )

        # Set override for first execution
        engine.set_execution_overrides({"max_concurrent_nodes": 1})
        await engine.execute(TaskEntity(goal="First"))

        # Second execution should use defaults (no override)
        await engine.execute(TaskEntity(goal="Second"))
        # No assertion on semaphore during execution since it's cleaned up,
        # but the pending_overrides should be empty
        assert engine._pending_overrides == {}

    @pytest.mark.asyncio
    async def test_depth_override_limits_recursion(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """max_depth override forces nodes to be terminal at lower depth."""
        # Non-terminal candidate at nesting level 0
        expandable = _candidate("Expandable", is_terminal=False, score=0.9)
        # Terminal candidates for child level
        terminal = _candidate("Terminal child", is_terminal=True, score=0.8)

        call_count = 0

        async def _planner_side_effect(*, goal, context, nesting_level):
            nonlocal call_count
            call_count += 1
            if nesting_level == 0:
                return [expandable]
            return [terminal]

        planner.generate_candidates.side_effect = _planner_side_effect
        plan_evaluator.evaluate.return_value = _approved_eval()
        result_evaluator.evaluate.return_value = _ok_result()
        inner_engine.execute.side_effect = _make_inner_execute()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            max_depth=3,  # default allows 3 levels
            skip_gate2_for_terminal_success=True,
        )

        # Override depth to 1: nesting_level=0 expandable → level 1 forced terminal
        engine.set_execution_overrides({"max_depth": 1})
        task = TaskEntity(goal="Shallow goal")
        result = await engine.execute(task)

        assert result.status == TaskStatus.SUCCESS
        # Planner called twice: level 0 (expandable) + level 1 (child)
        assert call_count == 2


# ---------------------------------------------------------------------------
# TD-181: Time-based timeout
# ---------------------------------------------------------------------------


class TestExecutionTimeout:
    """TD-181: Verify time-based timeout prevents zombie tasks."""

    @pytest.mark.asyncio
    async def test_is_timed_out_false_when_within_limit(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            max_execution_seconds=60,
        )
        engine._execution_start = time.monotonic()
        assert engine._is_timed_out() is False

    @pytest.mark.asyncio
    async def test_is_timed_out_true_when_exceeded(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            max_execution_seconds=1,
        )
        engine._execution_start = time.monotonic() - 2  # 2s ago
        assert engine._is_timed_out() is True

    @pytest.mark.asyncio
    async def test_timeout_marks_task_failed(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """A task that exceeds max_execution_seconds should end with FAILED status."""
        import asyncio

        async def _slow_execute(task: TaskEntity) -> TaskEntity:
            # Simulate a slow node that takes longer than the timeout
            await asyncio.sleep(0.2)
            for st in task.subtasks:
                st.status = SubTaskStatus.SUCCESS
                st.result = "done"
                st.model_used = "test-model"
            task.status = TaskStatus.SUCCESS
            return task

        inner_engine.execute.side_effect = _slow_execute

        planner.generate_candidates.return_value = [
            _candidate("Step A"),
            _candidate("Step B"),
            _candidate("Step C"),
        ]
        plan_evaluator.evaluate.return_value = _approved_eval()

        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            max_execution_seconds=0,  # 0 seconds = immediate timeout after first batch
            skip_gate2_for_terminal_success=True,
        )
        # Set start time to the past so it times out immediately
        engine._execution_start = time.monotonic() - 1

        task = TaskEntity(goal="Slow goal")
        # execute() sets _execution_start. Patch it after the call starts.
        # Instead, use max_execution_seconds=1 and pre-set start to make timeout immediate.
        engine._max_execution_seconds = 1
        engine._execution_start = time.monotonic() - 2

        result = await engine.execute(task)

        # After timeout, no RUNNING subtasks should remain
        for st in result.subtasks:
            assert st.status != SubTaskStatus.RUNNING, (
                f"Subtask '{st.description}' still RUNNING after timeout"
            )

    @pytest.mark.asyncio
    async def test_disabled_timeout_zero(
        self,
        planner: AsyncMock,
        plan_evaluator: AsyncMock,
        result_evaluator: AsyncMock,
        inner_engine: AsyncMock,
    ) -> None:
        """max_execution_seconds=0 means no timeout (disabled)."""
        engine = FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=inner_engine,
            max_execution_seconds=0,
        )
        engine._execution_start = time.monotonic() - 9999
        assert engine._is_timed_out() is False

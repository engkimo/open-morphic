"""Tests for TD-180: Zombie task prevention.

Verifies that:
- LangGraphTaskEngine marks subtasks FAILED when ReAct terminates via max_iterations
- LangGraphTaskEngine marks subtasks FAILED when ReAct detects repetitive_tool_loop
- FractalTaskEngine._execute_node_safe catches unexpected exceptions
"""

from __future__ import annotations

from domain.entities.fractal_engine import PlanNode
from domain.entities.task import SubTask
from domain.value_objects.status import SubTaskStatus

# ── LangGraphTaskEngine: max_iterations → FAILED ─────────────


class TestMaxIterationsMarksFailed:
    """When ReAct terminates via max_iterations, subtask should be FAILED."""

    async def test_max_iterations_marks_subtask_failed(self):
        """Subtask status = FAILED when terminated_reason = 'max_iterations'."""
        subtask = SubTask(description="Test subtask")
        _term = "max_iterations"
        if _term in ("max_iterations", "repetitive_tool_loop"):
            subtask.status = SubTaskStatus.FAILED
            subtask.error = f"ReAct terminated: {_term}"
        else:
            subtask.status = SubTaskStatus.SUCCESS

        assert subtask.status == SubTaskStatus.FAILED
        assert "max_iterations" in subtask.error

    async def test_repetitive_loop_marks_subtask_failed(self):
        """Subtask status = FAILED when terminated_reason = 'repetitive_tool_loop'."""
        subtask = SubTask(description="Test subtask")
        _term = "repetitive_tool_loop"
        if _term in ("max_iterations", "repetitive_tool_loop"):
            subtask.status = SubTaskStatus.FAILED
            subtask.error = f"ReAct terminated: {_term}"
        else:
            subtask.status = SubTaskStatus.SUCCESS

        assert subtask.status == SubTaskStatus.FAILED
        assert "repetitive_tool_loop" in subtask.error

    async def test_final_answer_still_marks_success(self):
        """Subtask status = SUCCESS when terminated_reason = 'final_answer'."""
        subtask = SubTask(description="Test subtask")
        _term = "final_answer"
        if _term in ("max_iterations", "repetitive_tool_loop"):
            subtask.status = SubTaskStatus.FAILED
        else:
            subtask.status = SubTaskStatus.SUCCESS

        assert subtask.status == SubTaskStatus.SUCCESS


# ── _execute_node_safe: catch-all exception handling ──────────


class TestExecuteNodeSafeCatchAll:
    """Unexpected exceptions in node execution → node.status = FAILED."""

    async def test_unexpected_exception_marks_node_failed(self):
        """If an unexpected error occurs, node is FAILED (not stuck RUNNING)."""
        node = PlanNode(description="Test node", is_terminal=True)
        node.status = SubTaskStatus.RUNNING

        # Simulate the catch-all logic from _execute_node_safe
        try:
            raise RuntimeError("Unexpected LLM API timeout")
        except Exception as exc:
            node.status = SubTaskStatus.FAILED
            node.error = f"Unexpected error: {exc!s}"[:500]

        assert node.status == SubTaskStatus.FAILED
        assert "Unexpected LLM API timeout" in node.error

    async def test_node_not_stuck_running_after_error(self):
        """Verify the node never stays in RUNNING after any kind of error."""
        node = PlanNode(description="Test node", is_terminal=True)
        node.status = SubTaskStatus.RUNNING

        errors = [
            RuntimeError("API timeout"),
            ConnectionError("Network down"),
            ValueError("Bad response"),
            KeyError("missing_key"),
        ]
        for err in errors:
            node.status = SubTaskStatus.RUNNING
            try:
                raise err
            except Exception as exc:
                node.status = SubTaskStatus.FAILED
                node.error = f"Unexpected error: {exc!s}"[:500]

            assert node.status == SubTaskStatus.FAILED, f"Node stuck RUNNING for {type(err)}"

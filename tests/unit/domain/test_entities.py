"""TDD: Domain entity tests — strict Pydantic validation."""

import pytest
from pydantic import ValidationError

from domain.entities.cost import CostRecord
from domain.entities.execution import Action, Observation, UndoAction
from domain.entities.memory import MemoryEntry
from domain.entities.task import SubTask, TaskEntity
from domain.value_objects import RiskLevel
from domain.value_objects.status import (
    MemoryType,
    ObservationStatus,
    SubTaskStatus,
    TaskStatus,
)


# ══════════════════════════════════════════════════════════════════
#  TaskEntity — core DAG node
# ══════════════════════════════════════════════════════════════════


class TestTaskEntity:
    def test_create_task(self):
        task = TaskEntity(goal="Implement fibonacci")
        assert task.goal == "Implement fibonacci"
        assert task.status == TaskStatus.PENDING
        assert task.subtasks == []
        assert task.total_cost_usd == 0.0

    def test_get_ready_subtasks_no_deps(self):
        task = TaskEntity(
            goal="Test",
            subtasks=[
                SubTask(id="a", description="step A"),
                SubTask(id="b", description="step B"),
            ],
        )
        ready = task.get_ready_subtasks()
        assert len(ready) == 2

    def test_get_ready_subtasks_with_deps(self):
        task = TaskEntity(
            goal="Test",
            subtasks=[
                SubTask(id="a", description="step A"),
                SubTask(id="b", description="step B", dependencies=["a"]),
            ],
        )
        ready = task.get_ready_subtasks()
        assert len(ready) == 1
        assert ready[0].id == "a"

    def test_get_ready_after_completion(self):
        task = TaskEntity(
            goal="Test",
            subtasks=[
                SubTask(id="a", description="step A", status=SubTaskStatus.SUCCESS),
                SubTask(id="b", description="step B", dependencies=["a"]),
            ],
        )
        ready = task.get_ready_subtasks()
        assert len(ready) == 1
        assert ready[0].id == "b"

    def test_mark_subtask(self):
        task = TaskEntity(
            goal="Test",
            subtasks=[SubTask(id="a", description="step A")],
        )
        task.mark_subtask("a", SubTaskStatus.SUCCESS, "done")
        assert task.subtasks[0].status == SubTaskStatus.SUCCESS
        assert task.subtasks[0].result == "done"

    def test_is_complete(self):
        task = TaskEntity(
            goal="Test",
            subtasks=[
                SubTask(id="a", description="A", status=SubTaskStatus.SUCCESS),
                SubTask(id="b", description="B", status=SubTaskStatus.FAILED),
            ],
        )
        assert task.is_complete is True

    def test_is_not_complete(self):
        task = TaskEntity(
            goal="Test",
            subtasks=[
                SubTask(id="a", description="A", status=SubTaskStatus.SUCCESS),
                SubTask(id="b", description="B", status=SubTaskStatus.PENDING),
            ],
        )
        assert task.is_complete is False

    def test_success_rate(self):
        task = TaskEntity(
            goal="Test",
            subtasks=[
                SubTask(id="a", description="A", status=SubTaskStatus.SUCCESS),
                SubTask(id="b", description="B", status=SubTaskStatus.FAILED),
                SubTask(id="c", description="C", status=SubTaskStatus.SUCCESS),
            ],
        )
        assert abs(task.success_rate - 2 / 3) < 0.01


# ══════════════════════════════════════════════════════════════════
#  Action / Observation / UndoAction
# ══════════════════════════════════════════════════════════════════


class TestAction:
    def test_default_risk(self):
        action = Action(tool="fs_read", args={"path": "/tmp/test"})
        assert action.risk == RiskLevel.SAFE

    def test_custom_risk(self):
        action = Action(tool="fs_delete", risk=RiskLevel.HIGH)
        assert action.risk == RiskLevel.HIGH


class TestObservation:
    def test_success(self):
        obs = Observation(status=ObservationStatus.SUCCESS, result="hello")
        assert obs.status == ObservationStatus.SUCCESS

    def test_denied(self):
        obs = Observation(status=ObservationStatus.DENIED, result="User denied")
        assert obs.status == ObservationStatus.DENIED


# ══════════════════════════════════════════════════════════════════
#  MemoryEntry
# ══════════════════════════════════════════════════════════════════


class TestMemoryEntry:
    def test_reinforce(self):
        entry = MemoryEntry(content="test", memory_type=MemoryType.L2_SEMANTIC)
        original_count = entry.access_count
        entry.reinforce()
        assert entry.access_count == original_count + 1


# ══════════════════════════════════════════════════════════════════
#  CostRecord
# ══════════════════════════════════════════════════════════════════


class TestCostRecord:
    def test_local_model(self):
        record = CostRecord(model="ollama/qwen3:8b", is_local=True)
        assert record.cost_usd == 0.0
        assert record.is_local is True

    def test_api_model(self):
        record = CostRecord(
            model="claude-sonnet-4-6",
            prompt_tokens=1000,
            completion_tokens=500,
            cost_usd=0.0045,
        )
        assert record.cost_usd == 0.0045
        assert record.is_local is False


# ══════════════════════════════════════════════════════════════════
#  Strict Validation Tests — ConfigDict(strict=True) enforcement
# ══════════════════════════════════════════════════════════════════


class TestStrictTaskValidation:
    def test_rejects_empty_goal(self):
        with pytest.raises(ValidationError):
            TaskEntity(goal="")

    def test_rejects_negative_cost(self):
        with pytest.raises(ValidationError):
            TaskEntity(goal="test", total_cost_usd=-1.0)

    def test_rejects_invalid_status_string(self):
        with pytest.raises(ValidationError):
            TaskEntity(goal="test", status="invalid")

    def test_rejects_raw_string_status(self):
        """strict=True: raw string 'pending' rejected, must use TaskStatus enum."""
        with pytest.raises(ValidationError):
            TaskEntity(goal="test", status="pending")


class TestStrictSubTaskValidation:
    def test_rejects_empty_description(self):
        with pytest.raises(ValidationError):
            SubTask(description="")

    def test_rejects_negative_cost(self):
        with pytest.raises(ValidationError):
            SubTask(description="test", cost_usd=-0.01)

    def test_rejects_raw_string_status(self):
        with pytest.raises(ValidationError):
            SubTask(description="test", status="pending")


class TestStrictActionValidation:
    def test_rejects_empty_tool(self):
        with pytest.raises(ValidationError):
            Action(tool="")

    def test_rejects_non_string_tool(self):
        with pytest.raises(ValidationError):
            Action(tool=123)


class TestStrictObservationValidation:
    def test_rejects_invalid_status(self):
        with pytest.raises(ValidationError):
            Observation(status="invalid_status")

    def test_rejects_raw_string_status(self):
        with pytest.raises(ValidationError):
            Observation(status="success")


class TestStrictMemoryValidation:
    def test_rejects_empty_content(self):
        with pytest.raises(ValidationError):
            MemoryEntry(content="", memory_type=MemoryType.L2_SEMANTIC)

    def test_rejects_invalid_memory_type(self):
        with pytest.raises(ValidationError):
            MemoryEntry(content="test", memory_type="invalid")

    def test_rejects_raw_string_memory_type(self):
        with pytest.raises(ValidationError):
            MemoryEntry(content="test", memory_type="l2_semantic")

    def test_rejects_importance_over_1(self):
        with pytest.raises(ValidationError):
            MemoryEntry(
                content="test",
                memory_type=MemoryType.L2_SEMANTIC,
                importance_score=1.5,
            )

    def test_rejects_negative_importance(self):
        with pytest.raises(ValidationError):
            MemoryEntry(
                content="test",
                memory_type=MemoryType.L2_SEMANTIC,
                importance_score=-0.1,
            )

    def test_rejects_zero_access_count(self):
        with pytest.raises(ValidationError):
            MemoryEntry(
                content="test",
                memory_type=MemoryType.L2_SEMANTIC,
                access_count=0,
            )


class TestStrictCostValidation:
    def test_rejects_empty_model(self):
        with pytest.raises(ValidationError):
            CostRecord(model="")

    def test_rejects_negative_prompt_tokens(self):
        with pytest.raises(ValidationError):
            CostRecord(model="test", prompt_tokens=-1)

    def test_rejects_negative_completion_tokens(self):
        with pytest.raises(ValidationError):
            CostRecord(model="test", completion_tokens=-1)

    def test_rejects_negative_cost(self):
        with pytest.raises(ValidationError):
            CostRecord(model="test", cost_usd=-0.01)

    def test_rejects_negative_cached_tokens(self):
        with pytest.raises(ValidationError):
            CostRecord(model="test", cached_tokens=-1)

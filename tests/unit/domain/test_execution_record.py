"""Tests for ExecutionRecord entity."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from domain.entities.execution_record import ExecutionRecord
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType


class TestExecutionRecord:
    def test_create_minimal(self) -> None:
        record = ExecutionRecord(
            task_id="t1",
            task_type=TaskType.SIMPLE_QA,
            engine_used=AgentEngineType.OLLAMA,
        )
        assert record.task_id == "t1"
        assert record.task_type == TaskType.SIMPLE_QA
        assert record.engine_used == AgentEngineType.OLLAMA
        assert record.success is False
        assert record.cost_usd == 0.0
        assert record.duration_seconds == 0.0
        assert record.cache_hit_rate == 0.0
        assert record.user_rating is None
        assert record.error_message is None
        assert record.model_used == ""
        assert record.goal == ""

    def test_create_full(self) -> None:
        now = datetime.now()
        record = ExecutionRecord(
            id="rec-123",
            task_id="t2",
            task_type=TaskType.CODE_GENERATION,
            goal="Write a fibonacci function",
            engine_used=AgentEngineType.CLAUDE_CODE,
            model_used="claude-sonnet-4-6",
            success=True,
            cost_usd=0.05,
            duration_seconds=12.5,
            cache_hit_rate=0.87,
            user_rating=4.5,
            created_at=now,
        )
        assert record.id == "rec-123"
        assert record.goal == "Write a fibonacci function"
        assert record.model_used == "claude-sonnet-4-6"
        assert record.success is True
        assert record.cost_usd == 0.05
        assert record.duration_seconds == 12.5
        assert record.cache_hit_rate == 0.87
        assert record.user_rating == 4.5
        assert record.created_at == now

    def test_auto_id_generation(self) -> None:
        r1 = ExecutionRecord(
            task_id="t1", task_type=TaskType.SIMPLE_QA, engine_used=AgentEngineType.OLLAMA
        )
        r2 = ExecutionRecord(
            task_id="t1", task_type=TaskType.SIMPLE_QA, engine_used=AgentEngineType.OLLAMA
        )
        assert r1.id != r2.id

    def test_auto_created_at(self) -> None:
        before = datetime.now()
        record = ExecutionRecord(
            task_id="t1", task_type=TaskType.SIMPLE_QA, engine_used=AgentEngineType.OLLAMA
        )
        after = datetime.now()
        assert before <= record.created_at <= after

    def test_empty_task_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionRecord(
                task_id="",
                task_type=TaskType.SIMPLE_QA,
                engine_used=AgentEngineType.OLLAMA,
            )

    def test_negative_cost_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionRecord(
                task_id="t1",
                task_type=TaskType.SIMPLE_QA,
                engine_used=AgentEngineType.OLLAMA,
                cost_usd=-0.01,
            )

    def test_negative_duration_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionRecord(
                task_id="t1",
                task_type=TaskType.SIMPLE_QA,
                engine_used=AgentEngineType.OLLAMA,
                duration_seconds=-1.0,
            )

    def test_cache_hit_rate_above_1_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionRecord(
                task_id="t1",
                task_type=TaskType.SIMPLE_QA,
                engine_used=AgentEngineType.OLLAMA,
                cache_hit_rate=1.1,
            )

    def test_cache_hit_rate_below_0_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionRecord(
                task_id="t1",
                task_type=TaskType.SIMPLE_QA,
                engine_used=AgentEngineType.OLLAMA,
                cache_hit_rate=-0.1,
            )

    def test_user_rating_above_5_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionRecord(
                task_id="t1",
                task_type=TaskType.SIMPLE_QA,
                engine_used=AgentEngineType.OLLAMA,
                user_rating=5.1,
            )

    def test_user_rating_below_0_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionRecord(
                task_id="t1",
                task_type=TaskType.SIMPLE_QA,
                engine_used=AgentEngineType.OLLAMA,
                user_rating=-0.1,
            )

    def test_all_task_types(self) -> None:
        for tt in TaskType:
            record = ExecutionRecord(task_id="t1", task_type=tt, engine_used=AgentEngineType.OLLAMA)
            assert record.task_type == tt

    def test_all_engine_types(self) -> None:
        for engine in AgentEngineType:
            record = ExecutionRecord(task_id="t1", task_type=TaskType.SIMPLE_QA, engine_used=engine)
            assert record.engine_used == engine

    def test_error_message_with_failure(self) -> None:
        record = ExecutionRecord(
            task_id="t1",
            task_type=TaskType.SIMPLE_QA,
            engine_used=AgentEngineType.OLLAMA,
            success=False,
            error_message="Connection refused",
        )
        assert record.error_message == "Connection refused"
        assert record.success is False

    def test_validate_assignment(self) -> None:
        record = ExecutionRecord(
            task_id="t1",
            task_type=TaskType.SIMPLE_QA,
            engine_used=AgentEngineType.OLLAMA,
        )
        record.success = True
        assert record.success is True
        record.cost_usd = 0.10
        assert record.cost_usd == 0.10

    def test_validate_assignment_rejects_invalid(self) -> None:
        record = ExecutionRecord(
            task_id="t1",
            task_type=TaskType.SIMPLE_QA,
            engine_used=AgentEngineType.OLLAMA,
        )
        with pytest.raises(ValidationError):
            record.cost_usd = -1.0

    def test_user_rating_none_allowed(self) -> None:
        record = ExecutionRecord(
            task_id="t1",
            task_type=TaskType.SIMPLE_QA,
            engine_used=AgentEngineType.OLLAMA,
            user_rating=None,
        )
        assert record.user_rating is None

    def test_user_rating_zero_allowed(self) -> None:
        record = ExecutionRecord(
            task_id="t1",
            task_type=TaskType.SIMPLE_QA,
            engine_used=AgentEngineType.OLLAMA,
            user_rating=0.0,
        )
        assert record.user_rating == 0.0

    def test_user_rating_five_allowed(self) -> None:
        record = ExecutionRecord(
            task_id="t1",
            task_type=TaskType.SIMPLE_QA,
            engine_used=AgentEngineType.OLLAMA,
            user_rating=5.0,
        )
        assert record.user_rating == 5.0

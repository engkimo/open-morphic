"""Tests for Strategy entities — RecoveryRule, ModelPreference, EnginePreference."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.entities.strategy import EnginePreference, ModelPreference, RecoveryRule
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType


class TestRecoveryRule:
    def test_create_minimal(self) -> None:
        rule = RecoveryRule(error_pattern="timeout", alternative_tool="shell_exec")
        assert rule.error_pattern == "timeout"
        assert rule.alternative_tool == "shell_exec"
        assert rule.failed_tool == ""
        assert rule.alternative_args == {}
        assert rule.success_count == 0
        assert rule.total_attempts == 0

    def test_create_full(self) -> None:
        rule = RecoveryRule(
            error_pattern="connection refused",
            failed_tool="browser_navigate",
            alternative_tool="web_fetch",
            alternative_args={"timeout": 30},
            success_count=5,
            total_attempts=7,
        )
        assert rule.failed_tool == "browser_navigate"
        assert rule.alternative_args == {"timeout": 30}
        assert rule.success_count == 5
        assert rule.total_attempts == 7

    def test_success_rate(self) -> None:
        rule = RecoveryRule(
            error_pattern="err",
            alternative_tool="alt",
            success_count=3,
            total_attempts=4,
        )
        assert rule.success_rate == 0.75

    def test_success_rate_zero_attempts(self) -> None:
        rule = RecoveryRule(error_pattern="err", alternative_tool="alt")
        assert rule.success_rate == 0.0

    def test_success_rate_perfect(self) -> None:
        rule = RecoveryRule(
            error_pattern="err",
            alternative_tool="alt",
            success_count=10,
            total_attempts=10,
        )
        assert rule.success_rate == 1.0

    def test_empty_error_pattern_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RecoveryRule(error_pattern="", alternative_tool="alt")

    def test_empty_alternative_tool_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RecoveryRule(error_pattern="err", alternative_tool="")

    def test_negative_success_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RecoveryRule(error_pattern="err", alternative_tool="alt", success_count=-1)

    def test_negative_total_attempts_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RecoveryRule(error_pattern="err", alternative_tool="alt", total_attempts=-1)


class TestModelPreference:
    def test_create_minimal(self) -> None:
        pref = ModelPreference(task_type=TaskType.SIMPLE_QA, model="ollama/qwen3:8b")
        assert pref.task_type == TaskType.SIMPLE_QA
        assert pref.model == "ollama/qwen3:8b"
        assert pref.success_rate == 0.0
        assert pref.avg_cost_usd == 0.0
        assert pref.avg_duration_seconds == 0.0
        assert pref.sample_count == 0

    def test_create_full(self) -> None:
        pref = ModelPreference(
            task_type=TaskType.CODE_GENERATION,
            model="claude-sonnet-4-6",
            success_rate=0.85,
            avg_cost_usd=0.05,
            avg_duration_seconds=10.0,
            sample_count=20,
        )
        assert pref.success_rate == 0.85
        assert pref.avg_cost_usd == 0.05
        assert pref.sample_count == 20

    def test_empty_model_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelPreference(task_type=TaskType.SIMPLE_QA, model="")

    def test_success_rate_above_1_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelPreference(task_type=TaskType.SIMPLE_QA, model="m", success_rate=1.1)

    def test_success_rate_below_0_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelPreference(task_type=TaskType.SIMPLE_QA, model="m", success_rate=-0.1)

    def test_negative_cost_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelPreference(task_type=TaskType.SIMPLE_QA, model="m", avg_cost_usd=-1.0)

    def test_negative_duration_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelPreference(task_type=TaskType.SIMPLE_QA, model="m", avg_duration_seconds=-1.0)

    def test_negative_sample_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelPreference(task_type=TaskType.SIMPLE_QA, model="m", sample_count=-1)

    def test_all_task_types(self) -> None:
        for tt in TaskType:
            pref = ModelPreference(task_type=tt, model="m")
            assert pref.task_type == tt


class TestEnginePreference:
    def test_create_minimal(self) -> None:
        pref = EnginePreference(
            task_type=TaskType.LONG_RUNNING_DEV, engine=AgentEngineType.OPENHANDS
        )
        assert pref.task_type == TaskType.LONG_RUNNING_DEV
        assert pref.engine == AgentEngineType.OPENHANDS
        assert pref.success_rate == 0.0
        assert pref.sample_count == 0

    def test_create_full(self) -> None:
        pref = EnginePreference(
            task_type=TaskType.COMPLEX_REASONING,
            engine=AgentEngineType.CLAUDE_CODE,
            success_rate=0.92,
            avg_cost_usd=0.10,
            avg_duration_seconds=30.0,
            sample_count=50,
        )
        assert pref.success_rate == 0.92
        assert pref.avg_cost_usd == 0.10
        assert pref.sample_count == 50

    def test_all_engines(self) -> None:
        for engine in AgentEngineType:
            pref = EnginePreference(task_type=TaskType.SIMPLE_QA, engine=engine)
            assert pref.engine == engine

    def test_success_rate_above_1_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EnginePreference(
                task_type=TaskType.SIMPLE_QA,
                engine=AgentEngineType.OLLAMA,
                success_rate=1.1,
            )

    def test_negative_cost_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EnginePreference(
                task_type=TaskType.SIMPLE_QA,
                engine=AgentEngineType.OLLAMA,
                avg_cost_usd=-1.0,
            )

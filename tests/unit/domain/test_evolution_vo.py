"""Tests for EvolutionLevel VO and ExecutionStats dataclass."""

from __future__ import annotations

from domain.ports.execution_record_repository import ExecutionStats
from domain.value_objects.evolution import EvolutionLevel


class TestEvolutionLevel:
    def test_tactical_value(self) -> None:
        assert EvolutionLevel.TACTICAL == "tactical"

    def test_strategic_value(self) -> None:
        assert EvolutionLevel.STRATEGIC == "strategic"

    def test_systemic_value(self) -> None:
        assert EvolutionLevel.SYSTEMIC == "systemic"

    def test_all_levels(self) -> None:
        assert len(EvolutionLevel) == 3

    def test_is_string_enum(self) -> None:
        assert isinstance(EvolutionLevel.TACTICAL, str)


class TestExecutionStats:
    def test_defaults(self) -> None:
        stats = ExecutionStats()
        assert stats.total_count == 0
        assert stats.success_count == 0
        assert stats.failure_count == 0
        assert stats.avg_cost_usd == 0.0
        assert stats.avg_duration_seconds == 0.0
        assert stats.model_distribution == {}
        assert stats.engine_distribution == {}

    def test_success_rate_empty(self) -> None:
        stats = ExecutionStats()
        assert stats.success_rate == 0.0

    def test_success_rate_computed(self) -> None:
        stats = ExecutionStats(total_count=10, success_count=7)
        assert stats.success_rate == 0.7

    def test_success_rate_perfect(self) -> None:
        stats = ExecutionStats(total_count=5, success_count=5)
        assert stats.success_rate == 1.0

    def test_success_rate_zero(self) -> None:
        stats = ExecutionStats(total_count=5, success_count=0)
        assert stats.success_rate == 0.0

    def test_with_distributions(self) -> None:
        stats = ExecutionStats(
            total_count=20,
            success_count=15,
            failure_count=5,
            avg_cost_usd=0.03,
            avg_duration_seconds=8.5,
            model_distribution={"ollama/qwen3:8b": 12, "claude-sonnet-4-6": 8},
            engine_distribution={"ollama": 12, "claude_code": 8},
        )
        assert stats.model_distribution["ollama/qwen3:8b"] == 12
        assert stats.engine_distribution["ollama"] == 12
        assert stats.success_rate == 0.75

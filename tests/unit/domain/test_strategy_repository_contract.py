"""Contract tests for StrategyRepository.

Parametrised across the in-memory fake and the file-backed concrete
implementation. Both must satisfy the same observable contract.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from domain.entities.strategy import EnginePreference, ModelPreference, RecoveryRule
from domain.ports.strategy_repository import StrategyRepository
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from infrastructure.evolution.strategy_store import StrategyStore
from tests.unit.application._fakes.in_memory_strategy_repository import (
    InMemoryStrategyRepository,
)


def _in_memory_factory(_tmp_path: Path) -> StrategyRepository:
    return InMemoryStrategyRepository()


def _file_backed_factory(tmp_path: Path) -> StrategyRepository:
    return StrategyStore(base_dir=tmp_path / "evolution")


@pytest.fixture(params=[_in_memory_factory, _file_backed_factory], ids=["in_memory", "file_backed"])
def repo(request, tmp_path: Path) -> StrategyRepository:
    factory: Callable[[Path], StrategyRepository] = request.param
    return factory(tmp_path)


class TestStrategyRepositoryContract:
    def test_load_recovery_rules_empty(self, repo: StrategyRepository) -> None:
        assert repo.load_recovery_rules() == []

    def test_load_model_preferences_empty(self, repo: StrategyRepository) -> None:
        assert repo.load_model_preferences() == []

    def test_load_engine_preferences_empty(self, repo: StrategyRepository) -> None:
        assert repo.load_engine_preferences() == []

    def test_append_recovery_rule_then_load(self, repo: StrategyRepository) -> None:
        rule = RecoveryRule(
            error_pattern="timeout",
            failed_tool="search",
            alternative_tool="cached_search",
        )
        repo.append_recovery_rule(rule)

        rules = repo.load_recovery_rules()
        assert len(rules) == 1
        assert rules[0].alternative_tool == "cached_search"

    def test_save_recovery_rules_overwrite(self, repo: StrategyRepository) -> None:
        first = RecoveryRule(error_pattern="a", alternative_tool="x")
        second = RecoveryRule(error_pattern="b", alternative_tool="y")

        repo.save_recovery_rules([first])
        repo.save_recovery_rules([second])

        rules = repo.load_recovery_rules()
        assert len(rules) == 1
        assert rules[0].error_pattern == "b"

    def test_save_model_preferences_round_trip(self, repo: StrategyRepository) -> None:
        prefs = [
            ModelPreference(
                task_type=TaskType.CODE_GENERATION,
                model="claude-sonnet-4-6",
                success_rate=0.9,
            ),
            ModelPreference(
                task_type=TaskType.SIMPLE_QA, model="qwen3:8b", success_rate=0.7
            ),
        ]

        repo.save_model_preferences(prefs)

        loaded = repo.load_model_preferences()
        assert len(loaded) == 2
        assert {p.model for p in loaded} == {"claude-sonnet-4-6", "qwen3:8b"}

    def test_save_engine_preferences_round_trip(self, repo: StrategyRepository) -> None:
        prefs = [
            EnginePreference(
                task_type=TaskType.CODE_GENERATION,
                engine=AgentEngineType.CLAUDE_CODE,
                success_rate=0.95,
            ),
        ]

        repo.save_engine_preferences(prefs)

        loaded = repo.load_engine_preferences()
        assert len(loaded) == 1
        assert loaded[0].engine == AgentEngineType.CLAUDE_CODE

    def test_idempotent_save_model_preferences(self, repo: StrategyRepository) -> None:
        prefs = [
            ModelPreference(task_type=TaskType.CODE_GENERATION, model="m", success_rate=0.5)
        ]

        repo.save_model_preferences(prefs)
        repo.save_model_preferences(prefs)

        assert len(repo.load_model_preferences()) == 1

"""Tests for UpdateStrategyUseCase."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from application.use_cases.update_strategy import UpdateStrategyUseCase
from domain.entities.execution_record import ExecutionRecord
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from infrastructure.evolution.strategy_store import StrategyStore
from infrastructure.persistence.in_memory_execution_record import (
    InMemoryExecutionRecordRepository,
)


def _rec(
    task_type: TaskType = TaskType.SIMPLE_QA,
    engine: AgentEngineType = AgentEngineType.OLLAMA,
    model: str = "ollama/qwen3:8b",
    success: bool = True,
    cost: float = 0.01,
    duration: float = 1.0,
    error: str | None = None,
) -> ExecutionRecord:
    return ExecutionRecord(
        task_id="t1",
        task_type=task_type,
        engine_used=engine,
        model_used=model,
        success=success,
        cost_usd=cost,
        duration_seconds=duration,
        error_message=error,
    )


class TestUpdateModelPreferences:
    def setup_method(self) -> None:
        self.repo = InMemoryExecutionRecordRepository()
        self.store = StrategyStore(base_dir=Path(tempfile.mkdtemp()))
        self.uc = UpdateStrategyUseCase(
            execution_repo=self.repo,
            strategy_store=self.store,
            min_samples=3,
        )

    @pytest.mark.asyncio
    async def test_empty_history(self) -> None:
        prefs = await self.uc.update_model_preferences()
        assert prefs == []

    @pytest.mark.asyncio
    async def test_below_min_samples(self) -> None:
        await self.repo.save(_rec())
        await self.repo.save(_rec())
        prefs = await self.uc.update_model_preferences()
        assert prefs == []

    @pytest.mark.asyncio
    async def test_above_min_samples(self) -> None:
        for _ in range(5):
            await self.repo.save(_rec(model="ollama/qwen3:8b", success=True, cost=0.0))
        prefs = await self.uc.update_model_preferences()
        assert len(prefs) == 1
        assert prefs[0].model == "ollama/qwen3:8b"
        assert prefs[0].success_rate == 1.0
        assert prefs[0].sample_count == 5

    @pytest.mark.asyncio
    async def test_multiple_models(self) -> None:
        for _ in range(3):
            await self.repo.save(_rec(model="model_a", success=True))
        for _ in range(3):
            await self.repo.save(_rec(model="model_b", success=False))
        prefs = await self.uc.update_model_preferences()
        assert len(prefs) == 2
        a = next(p for p in prefs if p.model == "model_a")
        b = next(p for p in prefs if p.model == "model_b")
        assert a.success_rate == 1.0
        assert b.success_rate == 0.0

    @pytest.mark.asyncio
    async def test_persists_to_store(self) -> None:
        for _ in range(3):
            await self.repo.save(_rec(model="m1"))
        await self.uc.update_model_preferences()
        loaded = self.store.load_model_preferences()
        assert len(loaded) == 1


class TestUpdateEnginePreferences:
    def setup_method(self) -> None:
        self.repo = InMemoryExecutionRecordRepository()
        self.store = StrategyStore(base_dir=Path(tempfile.mkdtemp()))
        self.uc = UpdateStrategyUseCase(
            execution_repo=self.repo,
            strategy_store=self.store,
            min_samples=3,
        )

    @pytest.mark.asyncio
    async def test_empty_history(self) -> None:
        prefs = await self.uc.update_engine_preferences()
        assert prefs == []

    @pytest.mark.asyncio
    async def test_engine_stats_computed(self) -> None:
        for _ in range(4):
            await self.repo.save(_rec(engine=AgentEngineType.OLLAMA, success=True, cost=0.0))
        for _ in range(4):
            await self.repo.save(_rec(engine=AgentEngineType.CLAUDE_CODE, success=True, cost=0.05))
        prefs = await self.uc.update_engine_preferences()
        assert len(prefs) == 2
        ollama_pref = next(p for p in prefs if p.engine == AgentEngineType.OLLAMA)
        claude_pref = next(p for p in prefs if p.engine == AgentEngineType.CLAUDE_CODE)
        assert ollama_pref.avg_cost_usd == 0.0
        assert claude_pref.avg_cost_usd == 0.05

    @pytest.mark.asyncio
    async def test_persists_to_store(self) -> None:
        for _ in range(3):
            await self.repo.save(_rec(engine=AgentEngineType.OLLAMA))
        await self.uc.update_engine_preferences()
        loaded = self.store.load_engine_preferences()
        assert len(loaded) == 1


class TestUpdateRecoveryRules:
    def setup_method(self) -> None:
        self.repo = InMemoryExecutionRecordRepository()
        self.store = StrategyStore(base_dir=Path(tempfile.mkdtemp()))
        self.uc = UpdateStrategyUseCase(
            execution_repo=self.repo,
            strategy_store=self.store,
            min_samples=3,
        )

    @pytest.mark.asyncio
    async def test_empty_history(self) -> None:
        rules = await self.uc.update_recovery_rules()
        assert rules == []

    @pytest.mark.asyncio
    async def test_no_rules_from_single_failure(self) -> None:
        await self.repo.save(_rec(success=False, error="timeout"))
        rules = await self.uc.update_recovery_rules()
        assert rules == []

    @pytest.mark.asyncio
    async def test_rule_from_repeated_failures(self) -> None:
        # 2 failures with same error on ollama
        await self.repo.save(_rec(success=False, error="timeout", engine=AgentEngineType.OLLAMA))
        await self.repo.save(_rec(success=False, error="timeout", engine=AgentEngineType.OLLAMA))
        # 1 success with same task type on claude_code
        await self.repo.save(_rec(success=True, engine=AgentEngineType.CLAUDE_CODE))
        rules = await self.uc.update_recovery_rules()
        assert len(rules) == 1
        assert rules[0].alternative_tool == "claude_code"

    @pytest.mark.asyncio
    async def test_no_duplicate_rules(self) -> None:
        # Create a pattern
        await self.repo.save(_rec(success=False, error="err", engine=AgentEngineType.OLLAMA))
        await self.repo.save(_rec(success=False, error="err", engine=AgentEngineType.OLLAMA))
        await self.repo.save(_rec(success=True, engine=AgentEngineType.CLAUDE_CODE))
        # First run creates rule
        rules1 = await self.uc.update_recovery_rules()
        assert len(rules1) == 1
        # Second run should not duplicate
        rules2 = await self.uc.update_recovery_rules()
        assert len(rules2) == 0


class TestRunFullUpdate:
    def setup_method(self) -> None:
        self.repo = InMemoryExecutionRecordRepository()
        self.store = StrategyStore(base_dir=Path(tempfile.mkdtemp()))
        self.uc = UpdateStrategyUseCase(
            execution_repo=self.repo,
            strategy_store=self.store,
            min_samples=2,
        )

    @pytest.mark.asyncio
    async def test_full_update_empty(self) -> None:
        result = await self.uc.run_full_update()
        assert result.model_preferences_updated == 0
        assert result.engine_preferences_updated == 0
        assert result.recovery_rules_added == 0
        assert result.details == []

    @pytest.mark.asyncio
    async def test_full_update_with_data(self) -> None:
        for _ in range(3):
            await self.repo.save(_rec(model="m1", success=True))
        result = await self.uc.run_full_update()
        assert result.model_preferences_updated >= 1
        assert len(result.details) >= 1

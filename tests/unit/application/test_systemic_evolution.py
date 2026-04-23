"""Tests for SystemicEvolutionUseCase."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from application.use_cases.analyze_execution import AnalyzeExecutionUseCase
from application.use_cases.discover_tools import DiscoverToolsUseCase, ToolSuggestions
from application.use_cases.systemic_evolution import SystemicEvolutionUseCase
from application.use_cases.update_strategy import UpdateStrategyUseCase
from domain.entities.execution_record import ExecutionRecord
from domain.entities.tool_candidate import ToolCandidate
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.evolution import EvolutionLevel
from domain.value_objects.model_tier import TaskType
from domain.value_objects.tool_safety import SafetyTier
from infrastructure.persistence.in_memory_execution_record import (
    InMemoryExecutionRecordRepository,
)
from tests.unit.application._fakes.in_memory_strategy_repository import (
    InMemoryStrategyRepository,
)


def _rec(
    success: bool = True,
    error: str | None = None,
    engine: AgentEngineType = AgentEngineType.OLLAMA,
) -> ExecutionRecord:
    return ExecutionRecord(
        task_id="t1",
        task_type=TaskType.SIMPLE_QA,
        engine_used=engine,
        model_used="ollama/qwen3:8b",
        success=success,
        error_message=error,
    )


def _candidate(name: str = "test-tool") -> ToolCandidate:
    return ToolCandidate(
        name=name,
        description="A test tool",
        publisher="test",
        package_name=name,
        transport="stdio",
        safety_tier=SafetyTier.COMMUNITY,
        safety_score=0.7,
    )


def _make_uc(
    repo: InMemoryExecutionRecordRepository | None = None,
    discover_tools: DiscoverToolsUseCase | None = None,
) -> SystemicEvolutionUseCase:
    repo = repo or InMemoryExecutionRecordRepository()
    store = InMemoryStrategyRepository()
    analyze = AnalyzeExecutionUseCase(repo=repo)
    update_strategy = UpdateStrategyUseCase(
        execution_repo=repo,
        strategy_store=store,
        min_samples=2,
    )
    return SystemicEvolutionUseCase(
        analyze_execution=analyze,
        update_strategy=update_strategy,
        discover_tools=discover_tools,
    )


class TestIdentifyToolGaps:
    @pytest.mark.asyncio
    async def test_empty_history(self) -> None:
        uc = _make_uc()
        gaps = await uc.identify_tool_gaps()
        assert gaps == []

    @pytest.mark.asyncio
    async def test_no_recurring_failures(self) -> None:
        repo = InMemoryExecutionRecordRepository()
        await repo.save(_rec(success=False, error="err1"))
        await repo.save(_rec(success=False, error="err2"))
        uc = _make_uc(repo=repo)
        gaps = await uc.identify_tool_gaps()
        assert gaps == []

    @pytest.mark.asyncio
    async def test_recurring_failures_detected(self) -> None:
        repo = InMemoryExecutionRecordRepository()
        for _ in range(3):
            await repo.save(_rec(success=False, error="Connection timeout"))
        uc = _make_uc(repo=repo)
        gaps = await uc.identify_tool_gaps()
        assert len(gaps) == 1
        assert "Connection timeout" in gaps[0]


class TestSuggestToolsForGaps:
    @pytest.mark.asyncio
    async def test_no_discover_tools(self) -> None:
        uc = _make_uc(discover_tools=None)
        suggested = await uc.suggest_tools_for_gaps(["timeout"])
        assert suggested == []

    @pytest.mark.asyncio
    async def test_empty_gaps(self) -> None:
        mock_discover = AsyncMock(spec=DiscoverToolsUseCase)
        uc = _make_uc(discover_tools=mock_discover)
        suggested = await uc.suggest_tools_for_gaps([])
        assert suggested == []

    @pytest.mark.asyncio
    async def test_suggests_tools(self) -> None:
        mock_discover = AsyncMock(spec=DiscoverToolsUseCase)
        mock_discover.suggest_for_failure.return_value = ToolSuggestions(
            suggestions=[_candidate("retry-tool")],
            queries_used=["timeout"],
        )
        uc = _make_uc(discover_tools=mock_discover)
        suggested = await uc.suggest_tools_for_gaps(["timeout error"])
        assert "retry-tool" in suggested

    @pytest.mark.asyncio
    async def test_deduplicates_suggestions(self) -> None:
        mock_discover = AsyncMock(spec=DiscoverToolsUseCase)
        mock_discover.suggest_for_failure.return_value = ToolSuggestions(
            suggestions=[_candidate("same-tool")],
            queries_used=["err"],
        )
        uc = _make_uc(discover_tools=mock_discover)
        suggested = await uc.suggest_tools_for_gaps(["err1", "err2"])
        assert suggested.count("same-tool") == 1


class TestRunEvolution:
    @pytest.mark.asyncio
    async def test_empty_report(self) -> None:
        uc = _make_uc()
        report = await uc.run_evolution()
        assert report.level == EvolutionLevel.SYSTEMIC
        assert report.summary == "No changes needed"
        assert report.tool_gaps_found == 0

    @pytest.mark.asyncio
    async def test_with_data(self) -> None:
        repo = InMemoryExecutionRecordRepository()
        for _ in range(5):
            await repo.save(_rec(success=True))
        uc = _make_uc(repo=repo)
        report = await uc.run_evolution()
        assert report.level == EvolutionLevel.SYSTEMIC
        assert report.strategy_update is not None

    @pytest.mark.asyncio
    async def test_with_gaps_and_tools(self) -> None:
        repo = InMemoryExecutionRecordRepository()
        for _ in range(4):
            await repo.save(_rec(success=False, error="timeout"))
        mock_discover = AsyncMock(spec=DiscoverToolsUseCase)
        mock_discover.suggest_for_failure.return_value = ToolSuggestions(
            suggestions=[_candidate("timeout-fix")],
            queries_used=["timeout"],
        )
        uc = _make_uc(repo=repo, discover_tools=mock_discover)
        report = await uc.run_evolution()
        assert report.tool_gaps_found >= 1
        assert "timeout-fix" in report.tools_suggested
        assert "tool gaps found" in report.summary

    @pytest.mark.asyncio
    async def test_report_has_created_at(self) -> None:
        uc = _make_uc()
        report = await uc.run_evolution()
        assert report.created_at is not None

    @pytest.mark.asyncio
    async def test_report_summary_with_strategy_updates(self) -> None:
        repo = InMemoryExecutionRecordRepository()
        for _ in range(3):
            await repo.save(_rec(success=True, engine=AgentEngineType.OLLAMA))
        uc = _make_uc(repo=repo)
        report = await uc.run_evolution()
        # Should mention preferences if any were updated
        if report.strategy_update and report.strategy_update.model_preferences_updated > 0:
            assert "preferences updated" in report.summary

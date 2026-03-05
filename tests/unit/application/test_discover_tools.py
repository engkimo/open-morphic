"""Tests for DiscoverToolsUseCase."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from application.use_cases.discover_tools import DiscoverToolsUseCase
from domain.entities.tool_candidate import ToolCandidate
from domain.ports.tool_registry import ToolSearchResult
from domain.value_objects.tool_safety import SafetyTier


def _candidate(name: str, score: float = 0.5) -> ToolCandidate:
    return ToolCandidate(
        name=name,
        safety_tier=SafetyTier.COMMUNITY,
        safety_score=score,
    )


@pytest.fixture
def registry() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def use_case(registry: AsyncMock) -> DiscoverToolsUseCase:
    return DiscoverToolsUseCase(registry=registry)


class TestDiscoverToolsUseCase:
    async def test_suggest_for_file_error(
        self, use_case: DiscoverToolsUseCase, registry: AsyncMock
    ) -> None:
        registry.search.return_value = ToolSearchResult(
            query="filesystem", candidates=[_candidate("filesystem", 0.8)], total_count=1
        )
        result = await use_case.suggest_for_failure("FileNotFoundError: config.yaml")
        assert len(result.suggestions) >= 1
        assert len(result.queries_used) >= 1

    async def test_suggest_no_matching_error(
        self, use_case: DiscoverToolsUseCase, registry: AsyncMock
    ) -> None:
        result = await use_case.suggest_for_failure("Unknown weird error")
        assert result.suggestions == []
        assert result.queries_used == []
        registry.search.assert_not_awaited()

    async def test_suggest_deduplicates(
        self, use_case: DiscoverToolsUseCase, registry: AsyncMock
    ) -> None:
        # Same tool returned for different queries
        c = _candidate("filesystem", 0.8)
        registry.search.return_value = ToolSearchResult(query="test", candidates=[c], total_count=1)
        result = await use_case.suggest_for_failure("file not found, Permission denied")
        names = [s.name for s in result.suggestions]
        assert names.count("filesystem") == 1

    async def test_suggest_sorts_by_score(
        self, use_case: DiscoverToolsUseCase, registry: AsyncMock
    ) -> None:
        c_low = _candidate("low-tool", 0.2)
        c_high = _candidate("high-tool", 0.9)
        registry.search.return_value = ToolSearchResult(
            query="test", candidates=[c_low, c_high], total_count=2
        )
        result = await use_case.suggest_for_failure("database connection refused 5432")
        assert result.suggestions[0].name == "high-tool"

    async def test_suggest_respects_max_results(
        self, use_case: DiscoverToolsUseCase, registry: AsyncMock
    ) -> None:
        candidates = [_candidate(f"tool-{i}", 0.5) for i in range(10)]
        registry.search.return_value = ToolSearchResult(
            query="test", candidates=candidates, total_count=10
        )
        result = await use_case.suggest_for_failure("database error", max_results=3)
        assert len(result.suggestions) <= 3

    async def test_suggest_with_task_context(
        self, use_case: DiscoverToolsUseCase, registry: AsyncMock
    ) -> None:
        registry.search.return_value = ToolSearchResult(
            query="web-search", candidates=[_candidate("web-search")], total_count=1
        )
        result = await use_case.suggest_for_failure(
            "timeout error",
            task_description="Search the web for data",
        )
        assert len(result.queries_used) >= 1

    async def test_suggest_queries_limited_to_three(
        self, use_case: DiscoverToolsUseCase, registry: AsyncMock
    ) -> None:
        registry.search.return_value = ToolSearchResult(query="test", candidates=[], total_count=0)
        # Trigger many pattern matches
        error = "file not found, database error, git repository, docker image, slack channel"
        result = await use_case.suggest_for_failure(error)
        assert len(result.queries_used) <= 3
        assert registry.search.await_count <= 3

    async def test_suggest_handles_registry_empty(
        self, use_case: DiscoverToolsUseCase, registry: AsyncMock
    ) -> None:
        registry.search.return_value = ToolSearchResult(query="test", candidates=[], total_count=0)
        result = await use_case.suggest_for_failure("FileNotFoundError: x")
        assert result.suggestions == []

    async def test_suggest_multiple_queries_combine(
        self, use_case: DiscoverToolsUseCase, registry: AsyncMock
    ) -> None:
        registry.search.side_effect = [
            ToolSearchResult(
                query="filesystem",
                candidates=[_candidate("fs-tool", 0.7)],
                total_count=1,
            ),
            ToolSearchResult(
                query="database",
                candidates=[_candidate("db-tool", 0.6)],
                total_count=1,
            ),
            ToolSearchResult(
                query="git",
                candidates=[_candidate("git-tool", 0.5)],
                total_count=1,
            ),
        ]
        result = await use_case.suggest_for_failure(
            "file not found and database error and git repository broken"
        )
        names = {s.name for s in result.suggestions}
        assert "fs-tool" in names
        assert "db-tool" in names

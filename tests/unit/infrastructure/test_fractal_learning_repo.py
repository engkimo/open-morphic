"""Tests for infrastructure/fractal/in_memory_learning_repo.py.

Sprint 15.7 (TD-105): In-memory learning repository tests.
"""

from __future__ import annotations

import pytest

from domain.entities.fractal_learning import ErrorPattern, SuccessfulPath
from infrastructure.fractal.in_memory_learning_repo import InMemoryFractalLearningRepository


@pytest.fixture()
def repo() -> InMemoryFractalLearningRepository:
    return InMemoryFractalLearningRepository()


# ── Error patterns ──


class TestErrorPatterns:
    async def test_save_and_find(self, repo: InMemoryFractalLearningRepository) -> None:
        p = ErrorPattern(
            goal_fragment="REST API",
            node_description="Setup project",
            error_message="timeout",
        )
        await repo.save_error_pattern(p)
        found = await repo.find_error_patterns("Build a REST API", "setup project")
        assert len(found) == 1
        assert found[0].error_message == "timeout"

    async def test_find_no_match(self, repo: InMemoryFractalLearningRepository) -> None:
        p = ErrorPattern(
            goal_fragment="REST API",
            node_description="Setup project",
            error_message="timeout",
        )
        await repo.save_error_pattern(p)
        found = await repo.find_error_patterns("CLI tool", "deploy")
        assert len(found) == 0

    async def test_save_duplicate_merges(self, repo: InMemoryFractalLearningRepository) -> None:
        p1 = ErrorPattern(
            goal_fragment="API",
            node_description="Setup",
            error_message="timeout",
        )
        p2 = ErrorPattern(
            goal_fragment="API",
            node_description="Setup",
            error_message="timeout",
        )
        await repo.save_error_pattern(p1)
        await repo.save_error_pattern(p2)
        all_patterns = await repo.list_error_patterns()
        assert len(all_patterns) == 1
        assert all_patterns[0].occurrence_count == 2

    async def test_list_ordered_by_count(self, repo: InMemoryFractalLearningRepository) -> None:
        p1 = ErrorPattern(
            goal_fragment="A",
            node_description="node1",
            error_message="err1",
            occurrence_count=3,
        )
        p2 = ErrorPattern(
            goal_fragment="B",
            node_description="node2",
            error_message="err2",
            occurrence_count=10,
        )
        await repo.save_error_pattern(p1)
        await repo.save_error_pattern(p2)
        patterns = await repo.list_error_patterns()
        assert patterns[0].occurrence_count == 10
        assert patterns[1].occurrence_count == 3

    async def test_list_limit(self, repo: InMemoryFractalLearningRepository) -> None:
        for i in range(5):
            await repo.save_error_pattern(
                ErrorPattern(
                    goal_fragment=f"g{i}",
                    node_description=f"n{i}",
                    error_message=f"e{i}",
                )
            )
        patterns = await repo.list_error_patterns(limit=3)
        assert len(patterns) == 3

    async def test_find_by_goal_matches(self, repo: InMemoryFractalLearningRepository) -> None:
        await repo.save_error_pattern(
            ErrorPattern(
                goal_fragment="REST API",
                node_description="Setup project",
                error_message="timeout",
            )
        )
        found = await repo.find_error_patterns_by_goal("Build a REST API server")
        assert len(found) == 1
        assert found[0].error_message == "timeout"

    async def test_find_by_goal_no_match(self, repo: InMemoryFractalLearningRepository) -> None:
        await repo.save_error_pattern(
            ErrorPattern(
                goal_fragment="REST API",
                node_description="Setup project",
                error_message="timeout",
            )
        )
        found = await repo.find_error_patterns_by_goal("CLI tool")
        assert len(found) == 0


# ── Successful paths ──


class TestSuccessfulPaths:
    async def test_save_and_find(self, repo: InMemoryFractalLearningRepository) -> None:
        sp = SuccessfulPath(
            goal_fragment="REST API",
            node_descriptions=["Setup", "Implement", "Test"],
            total_cost_usd=0.05,
        )
        await repo.save_successful_path(sp)
        found = await repo.find_successful_paths("Build a REST API")
        assert len(found) == 1
        assert len(found[0].node_descriptions) == 3

    async def test_find_no_match(self, repo: InMemoryFractalLearningRepository) -> None:
        sp = SuccessfulPath(
            goal_fragment="REST API",
            node_descriptions=["Setup"],
        )
        await repo.save_successful_path(sp)
        found = await repo.find_successful_paths("CLI tool")
        assert len(found) == 0

    async def test_save_duplicate_merges(self, repo: InMemoryFractalLearningRepository) -> None:
        sp1 = SuccessfulPath(
            goal_fragment="API",
            node_descriptions=["a", "b"],
            total_cost_usd=0.10,
        )
        sp2 = SuccessfulPath(
            goal_fragment="API",
            node_descriptions=["a", "b"],
            total_cost_usd=0.05,
        )
        await repo.save_successful_path(sp1)
        await repo.save_successful_path(sp2)
        all_paths = await repo.list_successful_paths()
        assert len(all_paths) == 1
        assert all_paths[0].usage_count == 2
        assert all_paths[0].total_cost_usd == pytest.approx(0.05)

    async def test_list_ordered_by_count(self, repo: InMemoryFractalLearningRepository) -> None:
        sp1 = SuccessfulPath(
            goal_fragment="A",
            node_descriptions=["x"],
            usage_count=2,
        )
        sp2 = SuccessfulPath(
            goal_fragment="B",
            node_descriptions=["y"],
            usage_count=7,
        )
        await repo.save_successful_path(sp1)
        await repo.save_successful_path(sp2)
        paths = await repo.list_successful_paths()
        assert paths[0].usage_count == 7

"""Tests for LLMPlanner learning integration — Sprint 16.3.

Verifies that the planner queries FractalLearningRepository and injects
learning context into the user message (not system prompt, per KV-cache
principle).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from domain.entities.fractal_learning import ErrorPattern, SuccessfulPath
from domain.ports.llm_gateway import LLMGateway, LLMResponse
from infrastructure.fractal.in_memory_learning_repo import (
    InMemoryFractalLearningRepository,
)
from infrastructure.fractal.llm_planner import LLMPlanner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _llm_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="test-model",
        prompt_tokens=50,
        completion_tokens=30,
        cost_usd=0.0,
    )


def _sample_json(count: int = 1) -> str:
    items = [
        {
            "description": f"Step {i + 1}",
            "is_terminal": True,
            "score": 0.8,
            "condition": None,
            "input_artifacts": {},
            "output_artifacts": {},
        }
        for i in range(count)
    ]
    return json.dumps(items)


@pytest.fixture()
def llm() -> AsyncMock:
    mock = AsyncMock(spec=LLMGateway)
    mock.complete.return_value = _llm_response(_sample_json(2))
    return mock


@pytest.fixture()
def repo() -> InMemoryFractalLearningRepository:
    return InMemoryFractalLearningRepository()


@pytest.fixture()
def planner_with_repo(llm: AsyncMock, repo: InMemoryFractalLearningRepository) -> LLMPlanner:
    return LLMPlanner(llm, candidates_per_node=3, max_depth=3, learning_repo=repo)


@pytest.fixture()
def planner_no_repo(llm: AsyncMock) -> LLMPlanner:
    return LLMPlanner(llm, candidates_per_node=3, max_depth=3)


# ===================================================================
# Learning context building
# ===================================================================


class TestLearningContextBuilding:
    @pytest.mark.asyncio
    async def test_no_repo_returns_empty(self, planner_no_repo: LLMPlanner) -> None:
        ctx = await planner_no_repo._build_learning_context("any goal")
        assert ctx == ""

    @pytest.mark.asyncio
    async def test_empty_repo_returns_empty(self, planner_with_repo: LLMPlanner) -> None:
        ctx = await planner_with_repo._build_learning_context("no matching goal")
        assert ctx == ""

    @pytest.mark.asyncio
    async def test_error_patterns_in_context(
        self,
        planner_with_repo: LLMPlanner,
        repo: InMemoryFractalLearningRepository,
    ) -> None:
        await repo.save_error_pattern(
            ErrorPattern(
                goal_fragment="REST API",
                node_description="Setup project",
                error_message="timeout exceeded",
                occurrence_count=5,
            )
        )
        ctx = await planner_with_repo._build_learning_context("Build a REST API")
        assert "AVOID" in ctx
        assert "Setup project" in ctx
        assert "timeout exceeded" in ctx
        assert "5x" in ctx

    @pytest.mark.asyncio
    async def test_successful_paths_in_context(
        self,
        planner_with_repo: LLMPlanner,
        repo: InMemoryFractalLearningRepository,
    ) -> None:
        await repo.save_successful_path(
            SuccessfulPath(
                goal_fragment="REST API",
                node_descriptions=["Design schema", "Implement endpoints", "Test"],
                total_cost_usd=0.05,
                usage_count=3,
            )
        )
        ctx = await planner_with_repo._build_learning_context("Build a REST API")
        assert "PREFER" in ctx
        assert "Design schema -> Implement endpoints -> Test" in ctx
        assert "$0.0500" in ctx
        assert "3x" in ctx

    @pytest.mark.asyncio
    async def test_both_patterns_and_paths(
        self,
        planner_with_repo: LLMPlanner,
        repo: InMemoryFractalLearningRepository,
    ) -> None:
        await repo.save_error_pattern(
            ErrorPattern(
                goal_fragment="API",
                node_description="Deploy",
                error_message="OOM",
            )
        )
        await repo.save_successful_path(
            SuccessfulPath(
                goal_fragment="API",
                node_descriptions=["Plan", "Code"],
                usage_count=2,
            )
        )
        ctx = await planner_with_repo._build_learning_context("Build API service")
        assert "AVOID" in ctx
        assert "PREFER" in ctx


# ===================================================================
# Limits
# ===================================================================


class TestLearningContextLimits:
    @pytest.mark.asyncio
    async def test_max_5_error_patterns(
        self,
        planner_with_repo: LLMPlanner,
        repo: InMemoryFractalLearningRepository,
    ) -> None:
        for i in range(10):
            await repo.save_error_pattern(
                ErrorPattern(
                    goal_fragment="api",
                    node_description=f"node_{i}",
                    error_message=f"err_{i}",
                    occurrence_count=10 - i,
                )
            )
        ctx = await planner_with_repo._build_learning_context("Build api")
        # Count lines with pattern indicator
        error_lines = [line for line in ctx.split("\n") if line.strip().startswith('- "')]
        assert len(error_lines) == 5

    @pytest.mark.asyncio
    async def test_max_3_successful_paths(
        self,
        planner_with_repo: LLMPlanner,
        repo: InMemoryFractalLearningRepository,
    ) -> None:
        for i in range(6):
            await repo.save_successful_path(
                SuccessfulPath(
                    goal_fragment="api",
                    node_descriptions=[f"step_{i}"],
                    usage_count=10 - i,
                )
            )
        ctx = await planner_with_repo._build_learning_context("Build api")
        path_lines = [line for line in ctx.split("\n") if line.strip().startswith("- [")]
        assert len(path_lines) == 3

    @pytest.mark.asyncio
    async def test_errors_sorted_by_occurrence(
        self,
        planner_with_repo: LLMPlanner,
        repo: InMemoryFractalLearningRepository,
    ) -> None:
        await repo.save_error_pattern(
            ErrorPattern(
                goal_fragment="api",
                node_description="low",
                error_message="e1",
                occurrence_count=2,
            )
        )
        await repo.save_error_pattern(
            ErrorPattern(
                goal_fragment="api",
                node_description="high",
                error_message="e2",
                occurrence_count=10,
            )
        )
        ctx = await planner_with_repo._build_learning_context("Build api")
        # "high" (10x) should appear before "low" (2x)
        assert ctx.index("10x") < ctx.index("2x")


# ===================================================================
# Resilience
# ===================================================================


class TestLearningContextResilience:
    @pytest.mark.asyncio
    async def test_repo_exception_ignored(self, llm: AsyncMock) -> None:
        broken_repo = AsyncMock()
        broken_repo.find_error_patterns_by_goal.side_effect = RuntimeError("DB down")
        planner = LLMPlanner(llm, learning_repo=broken_repo)

        ctx = await planner._build_learning_context("any goal")
        assert ctx == ""

    @pytest.mark.asyncio
    async def test_repo_error_still_generates_candidates(self, llm: AsyncMock) -> None:
        broken_repo = AsyncMock()
        broken_repo.find_error_patterns_by_goal.side_effect = RuntimeError("DB down")
        planner = LLMPlanner(llm, learning_repo=broken_repo)

        result = await planner.generate_candidates("Build API", "", 0)
        assert len(result) >= 1
        llm.complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_system_prompt_unchanged_with_learning(
        self,
        llm: AsyncMock,
        repo: InMemoryFractalLearningRepository,
    ) -> None:
        """System prompt must be identical with or without learning data."""
        await repo.save_error_pattern(
            ErrorPattern(
                goal_fragment="api",
                node_description="n",
                error_message="e",
            )
        )
        planner_with = LLMPlanner(llm, learning_repo=repo)
        planner_without = LLMPlanner(llm)

        msgs_with = planner_with._build_messages("Build api", "", 0, "forward", "ctx")
        msgs_without = planner_without._build_messages("Build api", "", 0, "forward")

        # System messages must be identical (KV-cache stability)
        assert msgs_with[0]["content"] == msgs_without[0]["content"]


# ===================================================================
# Backward compatibility
# ===================================================================


class TestBackwardCompatibility:
    @pytest.mark.asyncio
    async def test_no_repo_user_message_contains_goal(
        self, llm: AsyncMock, planner_no_repo: LLMPlanner
    ) -> None:
        """User message contains the goal plus per-request planning
        parameters (TD-190 moved direction/nesting/candidates out of system)."""
        await planner_no_repo.generate_candidates("Build a REST API", "", 0)
        messages = llm.complete.call_args[0][0]
        assert "Build a REST API" in messages[1]["content"]

    @pytest.mark.asyncio
    async def test_with_repo_user_message_contains_goal(
        self,
        llm: AsyncMock,
        planner_with_repo: LLMPlanner,
        repo: InMemoryFractalLearningRepository,
    ) -> None:
        await repo.save_error_pattern(
            ErrorPattern(
                goal_fragment="REST",
                node_description="n",
                error_message="e",
            )
        )
        await planner_with_repo.generate_candidates("Build REST API", "", 0)
        messages = llm.complete.call_args[0][0]
        user_msg = messages[1]["content"]
        assert "Build REST API" in user_msg
        assert "AVOID" in user_msg

"""Tests for CostTracker — LLM + engine cost tracking and budget control."""

from unittest.mock import AsyncMock

import pytest

from domain.ports.agent_engine import AgentEngineResult
from domain.ports.engine_cost_recorder import EngineCostRecorderPort
from domain.ports.llm_gateway import LLMResponse
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.persistence.in_memory import InMemoryCostRepository


@pytest.fixture
def repo() -> InMemoryCostRepository:
    return InMemoryCostRepository()


@pytest.fixture
def tracker(repo: InMemoryCostRepository) -> CostTracker:
    return CostTracker(repo)


def test_cost_tracker_is_an_engine_cost_recorder(tracker: CostTracker) -> None:
    assert isinstance(tracker, EngineCostRecorderPort)


def _make_response(
    model: str = "ollama/qwen3:8b",
    cost: float = 0.0,
    prompt: int = 10,
    completion: int = 5,
    cached: int = 0,
) -> LLMResponse:
    return LLMResponse(
        content="test",
        model=model,
        prompt_tokens=prompt,
        completion_tokens=completion,
        cost_usd=cost,
        cached_tokens=cached,
    )


class TestRecord:
    async def test_saves_to_repository(
        self, tracker: CostTracker, repo: InMemoryCostRepository
    ) -> None:
        await tracker.record(_make_response())
        assert len(repo.records) == 1
        assert repo.records[0].model == "ollama/qwen3:8b"

    async def test_marks_ollama_as_local(
        self, tracker: CostTracker, repo: InMemoryCostRepository
    ) -> None:
        await tracker.record(_make_response(model="ollama/qwen3:8b"))
        assert repo.records[0].is_local is True

    async def test_marks_api_as_not_local(
        self, tracker: CostTracker, repo: InMemoryCostRepository
    ) -> None:
        await tracker.record(_make_response(model="claude-sonnet-4-6", cost=0.003))
        assert repo.records[0].is_local is False

    async def test_preserves_cost(self, tracker: CostTracker, repo: InMemoryCostRepository) -> None:
        await tracker.record(_make_response(model="claude-sonnet-4-6", cost=0.005))
        assert repo.records[0].cost_usd == pytest.approx(0.005)

    async def test_preserves_token_counts(
        self, tracker: CostTracker, repo: InMemoryCostRepository
    ) -> None:
        await tracker.record(_make_response(prompt=100, completion=50))
        assert repo.records[0].prompt_tokens == 100
        assert repo.records[0].completion_tokens == 50

    async def test_propagates_cached_tokens(
        self, tracker: CostTracker, repo: InMemoryCostRepository
    ) -> None:
        await tracker.record(
            _make_response(model="claude-sonnet-4-6", prompt=200, cached=180, cost=0.001)
        )
        assert repo.records[0].cached_tokens == 180

    async def test_zero_cached_tokens_when_not_supplied(
        self, tracker: CostTracker, repo: InMemoryCostRepository
    ) -> None:
        await tracker.record(_make_response(prompt=100))
        assert repo.records[0].cached_tokens == 0


class TestQueries:
    async def test_daily_total(self, tracker: CostTracker) -> None:
        await tracker.record(_make_response(model="claude-sonnet-4-6", cost=0.01))
        await tracker.record(_make_response(model="gpt-4o-mini", cost=0.02))
        assert await tracker.get_daily_total() == pytest.approx(0.03)

    async def test_monthly_total_zero_for_local(self, tracker: CostTracker) -> None:
        await tracker.record(_make_response(cost=0.0))
        assert await tracker.get_monthly_total() == pytest.approx(0.0)

    async def test_local_usage_rate_all_local(self, tracker: CostTracker) -> None:
        await tracker.record(_make_response(model="ollama/qwen3:8b"))
        await tracker.record(_make_response(model="ollama/llama3.2:3b"))
        assert await tracker.get_local_usage_rate() == pytest.approx(1.0)

    async def test_local_usage_rate_mixed(self, tracker: CostTracker) -> None:
        await tracker.record(_make_response(model="ollama/qwen3:8b"))
        await tracker.record(_make_response(model="claude-sonnet-4-6", cost=0.01))
        assert await tracker.get_local_usage_rate() == pytest.approx(0.5)

    async def test_local_usage_rate_empty(self, tracker: CostTracker) -> None:
        assert await tracker.get_local_usage_rate() == pytest.approx(0.0)


class TestBudget:
    async def test_within_budget(self, tracker: CostTracker) -> None:
        await tracker.record(_make_response(model="claude-sonnet-4-6", cost=10.0))
        assert await tracker.check_budget(50.0) is True

    async def test_exceeded_budget(self, tracker: CostTracker) -> None:
        await tracker.record(_make_response(model="claude-opus-4-6", cost=60.0))
        assert await tracker.check_budget(50.0) is False

    async def test_exactly_at_budget(self, tracker: CostTracker) -> None:
        await tracker.record(_make_response(model="claude-sonnet-4-6", cost=50.0))
        assert await tracker.check_budget(50.0) is False


# ═══════════════════════════════════════════════════════════════
# BUG-002: Engine cost recording
# ═══════════════════════════════════════════════════════════════


def _make_engine_result(
    engine: AgentEngineType = AgentEngineType.CLAUDE_CODE,
    cost_usd: float = 0.05,
    model_used: str | None = "claude-sonnet-4-6",
    success: bool = True,
) -> AgentEngineResult:
    return AgentEngineResult(
        engine=engine,
        success=success,
        output="result",
        cost_usd=cost_usd,
        model_used=model_used,
    )


class TestRecordEngineResult:
    async def test_saves_engine_cost(
        self, tracker: CostTracker, repo: InMemoryCostRepository
    ) -> None:
        await tracker.record_engine_result(_make_engine_result(cost_usd=0.05))
        assert len(repo.records) == 1
        assert repo.records[0].cost_usd == pytest.approx(0.05)
        assert repo.records[0].engine_type == "claude_code"

    async def test_uses_model_name(
        self, tracker: CostTracker, repo: InMemoryCostRepository
    ) -> None:
        await tracker.record_engine_result(_make_engine_result(model_used="claude-sonnet-4-6"))
        assert repo.records[0].model == "claude-sonnet-4-6"

    async def test_falls_back_to_engine_prefix(
        self, tracker: CostTracker, repo: InMemoryCostRepository
    ) -> None:
        await tracker.record_engine_result(
            _make_engine_result(model_used=None, engine=AgentEngineType.GEMINI_CLI)
        )
        assert repo.records[0].model == "engine/gemini_cli"

    async def test_marks_ollama_as_local(
        self, tracker: CostTracker, repo: InMemoryCostRepository
    ) -> None:
        await tracker.record_engine_result(
            _make_engine_result(engine=AgentEngineType.OLLAMA, cost_usd=0.0)
        )
        assert repo.records[0].is_local is True

    async def test_marks_api_engines_not_local(
        self, tracker: CostTracker, repo: InMemoryCostRepository
    ) -> None:
        await tracker.record_engine_result(_make_engine_result(engine=AgentEngineType.CLAUDE_CODE))
        assert repo.records[0].is_local is False

    async def test_engine_cost_included_in_daily_total(self, tracker: CostTracker) -> None:
        await tracker.record(_make_response(model="claude-sonnet-4-6", cost=0.01))
        await tracker.record_engine_result(_make_engine_result(cost_usd=0.05))
        assert await tracker.get_daily_total() == pytest.approx(0.06)

    async def test_engine_cost_included_in_budget_check(self, tracker: CostTracker) -> None:
        await tracker.record_engine_result(_make_engine_result(cost_usd=45.0))
        assert await tracker.check_budget(50.0) is True
        await tracker.record_engine_result(_make_engine_result(cost_usd=10.0))
        assert await tracker.check_budget(50.0) is False

    async def test_error_swallowed(
        self, tracker: CostTracker, repo: InMemoryCostRepository
    ) -> None:
        """DB failure during recording should not raise."""
        repo.save = AsyncMock(side_effect=RuntimeError("DB down"))
        # Should not raise
        await tracker.record_engine_result(_make_engine_result())

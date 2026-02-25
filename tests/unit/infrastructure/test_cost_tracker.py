"""Tests for CostTracker — LLM cost tracking and budget control."""

import pytest

from domain.entities.cost import CostRecord
from domain.ports.cost_repository import CostRepository
from domain.ports.llm_gateway import LLMResponse
from infrastructure.llm.cost_tracker import CostTracker


class InMemoryCostRepository(CostRepository):
    """Test double implementing CostRepository port."""

    def __init__(self) -> None:
        self.records: list[CostRecord] = []

    async def save(self, record: CostRecord) -> None:
        self.records.append(record)

    async def get_daily_total(self) -> float:
        return sum(r.cost_usd for r in self.records)

    async def get_monthly_total(self) -> float:
        return sum(r.cost_usd for r in self.records)

    async def get_local_usage_rate(self) -> float:
        if not self.records:
            return 0.0
        local = sum(1 for r in self.records if r.is_local)
        return local / len(self.records)


@pytest.fixture
def repo() -> InMemoryCostRepository:
    return InMemoryCostRepository()


@pytest.fixture
def tracker(repo: InMemoryCostRepository) -> CostTracker:
    return CostTracker(repo)


def _make_response(
    model: str = "ollama/qwen3:8b",
    cost: float = 0.0,
    prompt: int = 10,
    completion: int = 5,
) -> LLMResponse:
    return LLMResponse(
        content="test",
        model=model,
        prompt_tokens=prompt,
        completion_tokens=completion,
        cost_usd=cost,
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

    async def test_preserves_cost(
        self, tracker: CostTracker, repo: InMemoryCostRepository
    ) -> None:
        await tracker.record(_make_response(model="claude-sonnet-4-6", cost=0.005))
        assert repo.records[0].cost_usd == pytest.approx(0.005)

    async def test_preserves_token_counts(
        self, tracker: CostTracker, repo: InMemoryCostRepository
    ) -> None:
        await tracker.record(_make_response(prompt=100, completion=50))
        assert repo.records[0].prompt_tokens == 100
        assert repo.records[0].completion_tokens == 50


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

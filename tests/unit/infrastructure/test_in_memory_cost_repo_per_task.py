"""TD-189 step 2: InMemoryCostRepository.get_cache_hit_rate_for_task.

RED → GREEN coverage for the per-task cache_hit_rate aggregation that
ExecuteTaskUseCase will use to populate ExecutionRecord.cache_hit_rate.
"""

from __future__ import annotations

import pytest

from domain.entities.cost import CostRecord
from infrastructure.persistence.in_memory import InMemoryCostRepository


@pytest.mark.asyncio
async def test_returns_zero_when_no_records() -> None:
    repo = InMemoryCostRepository()
    assert await repo.get_cache_hit_rate_for_task("missing") == 0.0


@pytest.mark.asyncio
async def test_returns_zero_when_only_other_tasks() -> None:
    repo = InMemoryCostRepository()
    await repo.save(
        CostRecord(
            model="claude-sonnet-4-6",
            prompt_tokens=100,
            cached_tokens=80,
            task_id="other",
        )
    )
    assert await repo.get_cache_hit_rate_for_task("target") == 0.0


@pytest.mark.asyncio
async def test_single_record_ratio() -> None:
    repo = InMemoryCostRepository()
    await repo.save(
        CostRecord(
            model="claude-sonnet-4-6",
            prompt_tokens=200,
            cached_tokens=800,
            task_id="t1",
        )
    )
    rate = await repo.get_cache_hit_rate_for_task("t1")
    assert rate == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_aggregates_multiple_records_for_same_task() -> None:
    repo = InMemoryCostRepository()
    await repo.save(
        CostRecord(
            model="claude-sonnet-4-6",
            prompt_tokens=100,
            cached_tokens=0,
            task_id="t1",
        )
    )
    await repo.save(
        CostRecord(
            model="claude-sonnet-4-6",
            prompt_tokens=300,
            cached_tokens=600,
            task_id="t1",
        )
    )
    rate = await repo.get_cache_hit_rate_for_task("t1")
    # cached=600, prompt=400, denom=1000 → 0.6
    assert rate == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_excludes_other_task_records() -> None:
    repo = InMemoryCostRepository()
    await repo.save(
        CostRecord(
            model="claude-sonnet-4-6",
            prompt_tokens=10,
            cached_tokens=90,
            task_id="t1",
        )
    )
    await repo.save(
        CostRecord(
            model="claude-sonnet-4-6",
            prompt_tokens=999,
            cached_tokens=0,
            task_id="t2",
        )
    )
    assert await repo.get_cache_hit_rate_for_task("t1") == pytest.approx(0.9)
    assert await repo.get_cache_hit_rate_for_task("t2") == 0.0


@pytest.mark.asyncio
async def test_zero_denominator_returns_zero() -> None:
    """Engine-only cost records (no token counts) must not divide by zero."""
    repo = InMemoryCostRepository()
    await repo.save(
        CostRecord(
            model="engine/codex_cli",
            prompt_tokens=0,
            cached_tokens=0,
            cost_usd=0.04,
            engine_type="codex_cli",
            task_id="t1",
        )
    )
    assert await repo.get_cache_hit_rate_for_task("t1") == 0.0


@pytest.mark.asyncio
async def test_records_without_task_id_are_ignored() -> None:
    repo = InMemoryCostRepository()
    await repo.save(
        CostRecord(
            model="claude-sonnet-4-6",
            prompt_tokens=100,
            cached_tokens=900,
        )  # task_id=None
    )
    assert await repo.get_cache_hit_rate_for_task("t1") == 0.0

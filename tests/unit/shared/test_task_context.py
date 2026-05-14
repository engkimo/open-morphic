"""TD-189 step 4: shared.task_context — ContextVar-based task_id propagation."""

from __future__ import annotations

import asyncio

import pytest

from shared.task_context import get_current_task_id, task_id_scope


def test_default_is_none() -> None:
    assert get_current_task_id() is None


def test_scope_sets_and_restores() -> None:
    assert get_current_task_id() is None
    with task_id_scope("task-A"):
        assert get_current_task_id() == "task-A"
    assert get_current_task_id() is None


def test_scope_resets_on_exception() -> None:
    with pytest.raises(RuntimeError), task_id_scope("task-B"):
        assert get_current_task_id() == "task-B"
        raise RuntimeError("boom")
    assert get_current_task_id() is None


def test_nested_scope() -> None:
    with task_id_scope("outer"):
        assert get_current_task_id() == "outer"
        with task_id_scope("inner"):
            assert get_current_task_id() == "inner"
        assert get_current_task_id() == "outer"
    assert get_current_task_id() is None


@pytest.mark.asyncio
async def test_async_scope_propagates_through_await() -> None:
    async def read_id() -> str | None:
        await asyncio.sleep(0)
        return get_current_task_id()

    with task_id_scope("async-task"):
        assert await read_id() == "async-task"


@pytest.mark.asyncio
async def test_concurrent_tasks_isolated() -> None:
    """asyncio.gather'd tasks must each carry their own scope."""

    async def run(task_id: str, observed: list[str | None]) -> None:
        with task_id_scope(task_id):
            await asyncio.sleep(0.01)
            observed.append(get_current_task_id())

    a: list[str | None] = []
    b: list[str | None] = []
    await asyncio.gather(run("alpha", a), run("beta", b))

    assert a == ["alpha"]
    assert b == ["beta"]
    assert get_current_task_id() is None

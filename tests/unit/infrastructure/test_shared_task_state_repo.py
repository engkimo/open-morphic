"""Tests for InMemorySharedTaskStateRepository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from domain.entities.cognitive import AgentAction, Decision, SharedTaskState
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.persistence.shared_task_state_repo import (
    InMemorySharedTaskStateRepository,
)


def _make_state(task_id: str = "task-1", **kwargs) -> SharedTaskState:
    return SharedTaskState(task_id=task_id, **kwargs)


def _make_decision(**kwargs) -> Decision:
    defaults = {
        "description": "chose Python",
        "agent_engine": AgentEngineType.CLAUDE_CODE,
    }
    defaults.update(kwargs)
    return Decision(**defaults)


def _make_action(**kwargs) -> AgentAction:
    defaults = {
        "agent_engine": AgentEngineType.CLAUDE_CODE,
        "action_type": "execute",
        "summary": "ran tests",
    }
    defaults.update(kwargs)
    return AgentAction(**defaults)


class TestSaveAndGet:
    @pytest.mark.asyncio
    async def test_save_and_get_basic(self):
        repo = InMemorySharedTaskStateRepository()
        state = _make_state()
        await repo.save(state)
        result = await repo.get("task-1")
        assert result is not None
        assert result.task_id == "task-1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self):
        repo = InMemorySharedTaskStateRepository()
        assert await repo.get("nope") is None

    @pytest.mark.asyncio
    async def test_save_overwrites(self):
        repo = InMemorySharedTaskStateRepository()
        await repo.save(_make_state(blockers=["b1"]))
        await repo.save(_make_state(blockers=["b2"]))
        result = await repo.get("task-1")
        assert result is not None
        assert result.blockers == ["b2"]


class TestListActive:
    @pytest.mark.asyncio
    async def test_returns_states_with_blockers(self):
        repo = InMemorySharedTaskStateRepository()
        s1 = _make_state("t1", blockers=["stuck"])
        s1.updated_at = datetime.now(tz=UTC) - timedelta(hours=48)
        await repo.save(s1)
        active = await repo.list_active()
        assert len(active) == 1
        assert active[0].task_id == "t1"

    @pytest.mark.asyncio
    async def test_returns_recently_updated(self):
        repo = InMemorySharedTaskStateRepository()
        s1 = _make_state("t1")
        s1.updated_at = datetime.now(tz=UTC) - timedelta(hours=1)
        await repo.save(s1)
        active = await repo.list_active()
        assert len(active) == 1

    @pytest.mark.asyncio
    async def test_excludes_stale_no_blockers(self):
        repo = InMemorySharedTaskStateRepository()
        s1 = _make_state("t1")
        s1.updated_at = datetime.now(tz=UTC) - timedelta(hours=48)
        await repo.save(s1)
        active = await repo.list_active()
        assert len(active) == 0

    @pytest.mark.asyncio
    async def test_sorted_by_updated_at_desc(self):
        repo = InMemorySharedTaskStateRepository()
        s1 = _make_state("t1")
        s1.updated_at = datetime.now(tz=UTC) - timedelta(hours=2)
        s2 = _make_state("t2")
        s2.updated_at = datetime.now(tz=UTC) - timedelta(hours=1)
        await repo.save(s1)
        await repo.save(s2)
        active = await repo.list_active()
        assert [s.task_id for s in active] == ["t2", "t1"]


class TestUpdateDecisions:
    @pytest.mark.asyncio
    async def test_updates_decisions(self):
        repo = InMemorySharedTaskStateRepository()
        await repo.save(_make_state())
        updated = _make_state(decisions=[_make_decision()])
        await repo.update_decisions(updated)
        result = await repo.get("task-1")
        assert result is not None
        assert len(result.decisions) == 1

    @pytest.mark.asyncio
    async def test_noop_if_not_found(self):
        repo = InMemorySharedTaskStateRepository()
        await repo.update_decisions(_make_state("nope"))
        # no error


class TestUpdateArtifacts:
    @pytest.mark.asyncio
    async def test_updates_artifacts(self):
        repo = InMemorySharedTaskStateRepository()
        await repo.save(_make_state())
        updated = _make_state(artifacts={"file.py": "created"})
        await repo.update_artifacts(updated)
        result = await repo.get("task-1")
        assert result is not None
        assert result.artifacts == {"file.py": "created"}


class TestAppendAction:
    @pytest.mark.asyncio
    async def test_appends_action(self):
        repo = InMemorySharedTaskStateRepository()
        await repo.save(_make_state())
        await repo.append_action("task-1", _make_action())
        result = await repo.get("task-1")
        assert result is not None
        assert len(result.agent_history) == 1

    @pytest.mark.asyncio
    async def test_noop_if_not_found(self):
        repo = InMemorySharedTaskStateRepository()
        await repo.append_action("nope", _make_action())


class TestDelete:
    @pytest.mark.asyncio
    async def test_deletes(self):
        repo = InMemorySharedTaskStateRepository()
        await repo.save(_make_state())
        await repo.delete("task-1")
        assert await repo.get("task-1") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_no_error(self):
        repo = InMemorySharedTaskStateRepository()
        await repo.delete("nope")

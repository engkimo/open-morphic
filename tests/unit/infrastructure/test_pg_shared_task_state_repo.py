"""Tests for PgSharedTaskStateRepository — Sprint 17.1.

Uses mock async sessions (no real DB in unit tests).
Follows the same _FakeSessionContext pattern as test_pg_fractal_learning_repo.py.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.entities.cognitive import AgentAction, Decision, SharedTaskState
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.persistence.models import SharedTaskStateModel
from infrastructure.persistence.pg_shared_task_state_repository import (
    PgSharedTaskStateRepository,
)

# ═══════════════════════════════════════════════════════════════
# Test helpers
# ═══════════════════════════════════════════════════════════════


class _FakeSessionContext:
    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *args: object) -> None:
        pass


def _mock_session_factory() -> tuple[MagicMock, AsyncMock]:
    session = AsyncMock()
    # session.add() is synchronous in SQLAlchemy AsyncSession — use MagicMock
    # to avoid "coroutine never awaited" RuntimeWarning.
    session.add = MagicMock()
    factory = MagicMock()
    factory.return_value = _FakeSessionContext(session)
    return factory, session


def _sample_state(**overrides: object) -> SharedTaskState:
    defaults = dict(
        task_id="task-abc",
        decisions=[
            Decision(
                description="use Claude for reasoning",
                rationale="best quality",
                agent_engine=AgentEngineType.CLAUDE_CODE,
                confidence=0.9,
            ),
        ],
        artifacts={"code": "print('hello')"},
        blockers=["waiting for API key"],
        agent_history=[
            AgentAction(
                agent_engine=AgentEngineType.OLLAMA,
                action_type="execute",
                summary="ran initial plan",
                cost_usd=0.0,
                duration_seconds=1.2,
            ),
        ],
    )
    defaults.update(overrides)
    return SharedTaskState(**defaults)


def _sample_model(**overrides: object) -> SharedTaskStateModel:
    state = _sample_state()
    defaults = dict(
        task_id="task-abc",
        decisions=[d.model_dump(mode="json") for d in state.decisions],
        artifacts=state.artifacts,
        blockers=state.blockers,
        agent_history=[a.model_dump(mode="json") for a in state.agent_history],
        created_at=datetime(2026, 3, 26),
        updated_at=datetime(2026, 3, 26),
    )
    defaults.update(overrides)
    return SharedTaskStateModel(**defaults)


# ═══════════════════════════════════════════════════════════════
# Mapping round-trip tests
# ═══════════════════════════════════════════════════════════════


class TestSharedTaskStateMapping:
    def test_entity_to_model(self) -> None:
        state = _sample_state()
        model = PgSharedTaskStateRepository._to_model(state)
        assert model.task_id == "task-abc"
        assert len(model.decisions) == 1
        assert model.decisions[0]["description"] == "use Claude for reasoning"
        assert model.artifacts == {"code": "print('hello')"}
        assert model.blockers == ["waiting for API key"]
        assert len(model.agent_history) == 1

    def test_model_to_entity(self) -> None:
        model = _sample_model()
        entity = PgSharedTaskStateRepository._to_entity(model)
        assert entity.task_id == "task-abc"
        assert len(entity.decisions) == 1
        assert entity.decisions[0].description == "use Claude for reasoning"
        assert entity.decisions[0].agent_engine == AgentEngineType.CLAUDE_CODE
        assert entity.artifacts == {"code": "print('hello')"}
        assert entity.blockers == ["waiting for API key"]
        assert len(entity.agent_history) == 1
        assert entity.agent_history[0].action_type == "execute"

    def test_round_trip(self) -> None:
        state = _sample_state()
        model = PgSharedTaskStateRepository._to_model(state)
        restored = PgSharedTaskStateRepository._to_entity(model)
        assert restored.task_id == state.task_id
        assert len(restored.decisions) == len(state.decisions)
        assert len(restored.agent_history) == len(state.agent_history)
        assert restored.artifacts == state.artifacts
        assert restored.blockers == state.blockers

    def test_empty_state(self) -> None:
        state = SharedTaskState(task_id="empty-task")
        model = PgSharedTaskStateRepository._to_model(state)
        assert model.decisions == []
        assert model.artifacts == {}
        assert model.blockers == []
        assert model.agent_history == []
        restored = PgSharedTaskStateRepository._to_entity(model)
        assert restored.decisions == []
        assert restored.artifacts == {}


# ═══════════════════════════════════════════════════════════════
# save tests
# ═══════════════════════════════════════════════════════════════


class TestSaveSharedTaskState:
    @pytest.mark.asyncio
    async def test_save_new_inserts(self) -> None:
        factory, session = _mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgSharedTaskStateRepository(factory)
        await repo.save(_sample_state())

        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_existing_updates(self) -> None:
        factory, session = _mock_session_factory()
        existing = _sample_model()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgSharedTaskStateRepository(factory)
        updated = _sample_state(blockers=["new blocker"])
        await repo.save(updated)

        assert existing.blockers == ["new blocker"]
        session.add.assert_not_called()
        session.commit.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════
# get tests
# ═══════════════════════════════════════════════════════════════


class TestGetSharedTaskState:
    @pytest.mark.asyncio
    async def test_found(self) -> None:
        factory, session = _mock_session_factory()
        model = _sample_model()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = model
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgSharedTaskStateRepository(factory)
        result = await repo.get("task-abc")

        assert result is not None
        assert result.task_id == "task-abc"
        assert len(result.decisions) == 1

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        factory, session = _mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgSharedTaskStateRepository(factory)
        result = await repo.get("nonexistent")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# list_active tests
# ═══════════════════════════════════════════════════════════════


class TestListActive:
    @pytest.mark.asyncio
    async def test_returns_entities(self) -> None:
        factory, session = _mock_session_factory()
        model = _sample_model()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [model]
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgSharedTaskStateRepository(factory)
        results = await repo.list_active()

        assert len(results) == 1
        assert results[0].task_id == "task-abc"

    @pytest.mark.asyncio
    async def test_empty(self) -> None:
        factory, session = _mock_session_factory()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgSharedTaskStateRepository(factory)
        results = await repo.list_active()
        assert results == []


# ═══════════════════════════════════════════════════════════════
# update_decisions tests
# ═══════════════════════════════════════════════════════════════


class TestUpdateDecisions:
    @pytest.mark.asyncio
    async def test_updates_existing(self) -> None:
        factory, session = _mock_session_factory()
        existing = _sample_model()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgSharedTaskStateRepository(factory)
        state = _sample_state()
        new_decision = Decision(
            description="switch to Gemini",
            rationale="long context",
            agent_engine=AgentEngineType.GEMINI_CLI,
        )
        state.decisions.append(new_decision)
        await repo.update_decisions(state)

        assert len(existing.decisions) == 2
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_noop_if_not_found(self) -> None:
        factory, session = _mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgSharedTaskStateRepository(factory)
        await repo.update_decisions(_sample_state())
        session.commit.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════
# update_artifacts tests
# ═══════════════════════════════════════════════════════════════


class TestUpdateArtifacts:
    @pytest.mark.asyncio
    async def test_updates_existing(self) -> None:
        factory, session = _mock_session_factory()
        existing = _sample_model()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgSharedTaskStateRepository(factory)
        state = _sample_state(artifacts={"report": "final version"})
        await repo.update_artifacts(state)

        assert existing.artifacts == {"report": "final version"}
        session.commit.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════
# append_action tests
# ═══════════════════════════════════════════════════════════════


class TestAppendAction:
    @pytest.mark.asyncio
    async def test_appends_to_existing(self) -> None:
        factory, session = _mock_session_factory()
        existing = _sample_model()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgSharedTaskStateRepository(factory)
        new_action = AgentAction(
            agent_engine=AgentEngineType.CLAUDE_CODE,
            action_type="review",
            summary="reviewed code",
            cost_usd=0.05,
        )
        await repo.append_action("task-abc", new_action)

        assert len(existing.agent_history) == 2
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_noop_if_not_found(self) -> None:
        factory, session = _mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgSharedTaskStateRepository(factory)
        action = AgentAction(
            agent_engine=AgentEngineType.OLLAMA,
            action_type="execute",
        )
        await repo.append_action("nonexistent", action)
        session.commit.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════
# delete tests
# ═══════════════════════════════════════════════════════════════


class TestDeleteSharedTaskState:
    @pytest.mark.asyncio
    async def test_deletes_existing(self) -> None:
        factory, session = _mock_session_factory()
        existing = _sample_model()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgSharedTaskStateRepository(factory)
        await repo.delete("task-abc")

        session.delete.assert_awaited_once_with(existing)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_noop_if_not_found(self) -> None:
        factory, session = _mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgSharedTaskStateRepository(factory)
        await repo.delete("nonexistent")
        session.delete.assert_not_awaited()
        session.commit.assert_not_awaited()

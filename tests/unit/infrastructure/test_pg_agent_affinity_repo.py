"""Tests for PgAgentAffinityRepository — Sprint 17.1.

Uses mock async sessions (no real DB in unit tests).
Follows the same _FakeSessionContext pattern as test_pg_fractal_learning_repo.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.entities.cognitive import AgentAffinityScore
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.persistence.models import AgentAffinityScoreModel
from infrastructure.persistence.pg_agent_affinity_repository import (
    PgAgentAffinityRepository,
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


def _sample_score(**overrides: object) -> AgentAffinityScore:
    defaults = dict(
        engine=AgentEngineType.OLLAMA,
        topic="python",
        familiarity=0.8,
        recency=0.6,
        success_rate=0.9,
        cost_efficiency=1.0,
        sample_count=10,
        last_used=datetime(2026, 3, 26),
    )
    defaults.update(overrides)
    return AgentAffinityScore(**defaults)


def _sample_model(**overrides: object) -> AgentAffinityScoreModel:
    defaults = dict(
        id=uuid.uuid4(),
        engine="ollama",
        topic="python",
        familiarity=0.8,
        recency=0.6,
        success_rate=0.9,
        cost_efficiency=1.0,
        sample_count=10,
        last_used=datetime(2026, 3, 26),
    )
    defaults.update(overrides)
    return AgentAffinityScoreModel(**defaults)


# ═══════════════════════════════════════════════════════════════
# Mapping round-trip tests
# ═══════════════════════════════════════════════════════════════


class TestAffinityMapping:
    def test_entity_to_model(self) -> None:
        score = _sample_score()
        model = PgAgentAffinityRepository._to_model(score)
        assert model.engine == "ollama"
        assert model.topic == "python"
        assert model.familiarity == 0.8
        assert model.success_rate == 0.9
        assert model.sample_count == 10

    def test_model_to_entity(self) -> None:
        model = _sample_model()
        entity = PgAgentAffinityRepository._to_entity(model)
        assert entity.engine == AgentEngineType.OLLAMA
        assert entity.topic == "python"
        assert entity.familiarity == 0.8
        assert entity.success_rate == 0.9
        assert entity.sample_count == 10

    def test_round_trip(self) -> None:
        score = _sample_score(
            engine=AgentEngineType.CLAUDE_CODE,
            topic="architecture",
            familiarity=0.95,
        )
        model = PgAgentAffinityRepository._to_model(score)
        model.id = uuid.uuid4()
        restored = PgAgentAffinityRepository._to_entity(model)
        assert restored.engine == AgentEngineType.CLAUDE_CODE
        assert restored.topic == "architecture"
        assert restored.familiarity == pytest.approx(0.95)

    def test_none_last_used(self) -> None:
        score = _sample_score(last_used=None)
        model = PgAgentAffinityRepository._to_model(score)
        assert model.last_used is None
        model.id = uuid.uuid4()
        restored = PgAgentAffinityRepository._to_entity(model)
        assert restored.last_used is None


# ═══════════════════════════════════════════════════════════════
# get tests
# ═══════════════════════════════════════════════════════════════


class TestGetAffinity:
    @pytest.mark.asyncio
    async def test_found(self) -> None:
        factory, session = _mock_session_factory()
        model = _sample_model()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = model
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgAgentAffinityRepository(factory)
        result = await repo.get(AgentEngineType.OLLAMA, "python")

        assert result is not None
        assert result.engine == AgentEngineType.OLLAMA
        assert result.topic == "python"

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        factory, session = _mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgAgentAffinityRepository(factory)
        result = await repo.get(AgentEngineType.OLLAMA, "unknown")

        assert result is None


# ═══════════════════════════════════════════════════════════════
# get_by_topic / get_by_engine tests
# ═══════════════════════════════════════════════════════════════


class TestGetByFilters:
    @pytest.mark.asyncio
    async def test_get_by_topic(self) -> None:
        factory, session = _mock_session_factory()
        model = _sample_model()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [model]
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgAgentAffinityRepository(factory)
        results = await repo.get_by_topic("python")

        assert len(results) == 1
        assert results[0].topic == "python"

    @pytest.mark.asyncio
    async def test_get_by_engine(self) -> None:
        factory, session = _mock_session_factory()
        model = _sample_model()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [model]
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgAgentAffinityRepository(factory)
        results = await repo.get_by_engine(AgentEngineType.OLLAMA)

        assert len(results) == 1
        assert results[0].engine == AgentEngineType.OLLAMA

    @pytest.mark.asyncio
    async def test_get_by_topic_empty(self) -> None:
        factory, session = _mock_session_factory()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgAgentAffinityRepository(factory)
        results = await repo.get_by_topic("nonexistent")
        assert results == []


# ═══════════════════════════════════════════════════════════════
# upsert tests
# ═══════════════════════════════════════════════════════════════


class TestUpsertAffinity:
    @pytest.mark.asyncio
    async def test_insert_new(self) -> None:
        factory, session = _mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgAgentAffinityRepository(factory)
        await repo.upsert(_sample_score())

        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_existing(self) -> None:
        factory, session = _mock_session_factory()
        existing = _sample_model(familiarity=0.3, sample_count=5)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgAgentAffinityRepository(factory)
        updated = _sample_score(familiarity=0.9, sample_count=15)
        await repo.upsert(updated)

        assert existing.familiarity == 0.9
        assert existing.sample_count == 15
        session.add.assert_not_called()
        session.commit.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════
# list_all tests
# ═══════════════════════════════════════════════════════════════


class TestListAllAffinity:
    @pytest.mark.asyncio
    async def test_list_all(self) -> None:
        factory, session = _mock_session_factory()
        models = [_sample_model(), _sample_model(engine="claude_code", topic="review")]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = models
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgAgentAffinityRepository(factory)
        results = await repo.list_all()

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_list_all_empty(self) -> None:
        factory, session = _mock_session_factory()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgAgentAffinityRepository(factory)
        results = await repo.list_all()
        assert results == []

"""Tests for PgFractalLearningRepository — Sprint 16.2.

Uses mock async sessions (no real DB in unit tests).
Follows the same _FakeSessionContext pattern as test_pg_repositories.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.entities.fractal_learning import ErrorPattern, SuccessfulPath
from infrastructure.persistence.models import (
    FractalErrorPatternModel,
    FractalSuccessfulPathModel,
)
from infrastructure.persistence.pg_fractal_learning_repository import (
    PgFractalLearningRepository,
)

# ═══════════════════════════════════════════════════════════════
# Test helpers — reuse the mock session pattern
# ═══════════════════════════════════════════════════════════════


class _FakeSessionContext:
    """Async context manager that returns the mock session."""

    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *args: object) -> None:
        pass


def _mock_session_factory() -> tuple[MagicMock, AsyncMock]:
    """Return (factory, session) pair."""
    session = AsyncMock()
    # session.add() is synchronous in SQLAlchemy AsyncSession — use MagicMock
    # to avoid "coroutine never awaited" RuntimeWarning.
    session.add = MagicMock()
    factory = MagicMock()
    factory.return_value = _FakeSessionContext(session)
    return factory, session


# ═══════════════════════════════════════════════════════════════
# Mapping round-trip tests
# ═══════════════════════════════════════════════════════════════


class TestErrorPatternMapping:
    def test_entity_to_model_and_back(self) -> None:
        pattern = ErrorPattern(
            goal_fragment="fibonacci",
            node_description="generate sequence",
            error_message="timeout exceeded",
            nesting_level=1,
            occurrence_count=3,
        )
        model = PgFractalLearningRepository._to_error_model(pattern)
        assert model.goal_fragment == "fibonacci"
        assert model.node_description == "generate sequence"
        assert model.error_message == "timeout exceeded"
        assert model.nesting_level == 1
        assert model.occurrence_count == 3

        # Round-trip needs a UUID on the model
        model.id = uuid.uuid4()
        entity = PgFractalLearningRepository._to_error_entity(model)
        assert entity.goal_fragment == "fibonacci"
        assert entity.node_description == "generate sequence"
        assert entity.error_message == "timeout exceeded"
        assert entity.nesting_level == 1
        assert entity.occurrence_count == 3


class TestSuccessfulPathMapping:
    def test_entity_to_model_and_back(self) -> None:
        path = SuccessfulPath(
            goal_fragment="sort algorithm",
            node_descriptions=["analyze input", "implement quicksort", "test"],
            nesting_level=0,
            total_cost_usd=0.05,
            usage_count=2,
        )
        model = PgFractalLearningRepository._to_path_model(path)
        assert model.goal_fragment == "sort algorithm"
        assert model.node_descriptions == ["analyze input", "implement quicksort", "test"]
        assert model.total_cost_usd == Decimal("0.05")
        assert model.usage_count == 2

        # Round-trip needs a UUID
        model.id = uuid.uuid4()
        entity = PgFractalLearningRepository._to_path_entity(model)
        assert entity.goal_fragment == "sort algorithm"
        assert entity.node_descriptions == ["analyze input", "implement quicksort", "test"]
        assert entity.total_cost_usd == pytest.approx(0.05)
        assert entity.usage_count == 2


# ═══════════════════════════════════════════════════════════════
# save_error_pattern tests
# ═══════════════════════════════════════════════════════════════


class TestSaveErrorPattern:
    @pytest.mark.asyncio
    async def test_new_pattern_inserts(self) -> None:
        factory, session = _mock_session_factory()
        # No existing match
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgFractalLearningRepository(factory)
        pattern = ErrorPattern(
            goal_fragment="test",
            node_description="step1",
            error_message="fail",
        )
        await repo.save_error_pattern(pattern)

        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_existing_pattern_merges(self) -> None:
        factory, session = _mock_session_factory()
        # Existing match found
        existing_model = FractalErrorPatternModel(
            id=uuid.uuid4(),
            goal_fragment="test",
            node_description="step1",
            error_message="fail",
            nesting_level=0,
            occurrence_count=5,
            first_seen=datetime(2026, 1, 1),
            last_seen=datetime(2026, 1, 1),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_model
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgFractalLearningRepository(factory)
        pattern = ErrorPattern(
            goal_fragment="test",
            node_description="step1",
            error_message="fail",
        )
        await repo.save_error_pattern(pattern)

        # Should increment count, not add
        assert existing_model.occurrence_count == 6
        session.add.assert_not_called()
        session.commit.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════
# save_successful_path tests
# ═══════════════════════════════════════════════════════════════


class TestSaveSuccessfulPath:
    @pytest.mark.asyncio
    async def test_new_path_inserts(self) -> None:
        factory, session = _mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgFractalLearningRepository(factory)
        path = SuccessfulPath(
            goal_fragment="sort",
            node_descriptions=["a", "b"],
            total_cost_usd=0.01,
        )
        await repo.save_successful_path(path)

        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_existing_path_merges_and_keeps_lower_cost(self) -> None:
        factory, session = _mock_session_factory()
        existing_model = FractalSuccessfulPathModel(
            id=uuid.uuid4(),
            goal_fragment="sort",
            node_descriptions=["a", "b"],
            nesting_level=0,
            total_cost_usd=Decimal("0.10"),
            usage_count=3,
            first_used=datetime(2026, 1, 1),
            last_used=datetime(2026, 1, 1),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_model
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgFractalLearningRepository(factory)
        path = SuccessfulPath(
            goal_fragment="sort",
            node_descriptions=["a", "b"],
            total_cost_usd=0.02,  # lower cost
        )
        await repo.save_successful_path(path)

        assert existing_model.usage_count == 4
        assert existing_model.total_cost_usd == Decimal("0.02")
        session.add.assert_not_called()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_existing_path_keeps_existing_cost_if_lower(self) -> None:
        factory, session = _mock_session_factory()
        existing_model = FractalSuccessfulPathModel(
            id=uuid.uuid4(),
            goal_fragment="sort",
            node_descriptions=["a", "b"],
            nesting_level=0,
            total_cost_usd=Decimal("0.01"),
            usage_count=2,
            first_used=datetime(2026, 1, 1),
            last_used=datetime(2026, 1, 1),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_model
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgFractalLearningRepository(factory)
        path = SuccessfulPath(
            goal_fragment="sort",
            node_descriptions=["a", "b"],
            total_cost_usd=0.50,  # higher cost
        )
        await repo.save_successful_path(path)

        assert existing_model.usage_count == 3
        # Cost stays at the existing lower value
        assert existing_model.total_cost_usd == Decimal("0.01")


# ═══════════════════════════════════════════════════════════════
# list_* tests
# ═══════════════════════════════════════════════════════════════


class TestListErrorPatterns:
    @pytest.mark.asyncio
    async def test_list_returns_entities(self) -> None:
        factory, session = _mock_session_factory()
        model = FractalErrorPatternModel(
            id=uuid.uuid4(),
            goal_fragment="test",
            node_description="step",
            error_message="err",
            nesting_level=0,
            occurrence_count=10,
            first_seen=datetime(2026, 1, 1),
            last_seen=datetime(2026, 3, 1),
        )
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [model]
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgFractalLearningRepository(factory)
        patterns = await repo.list_error_patterns(limit=10)

        assert len(patterns) == 1
        assert patterns[0].goal_fragment == "test"
        assert patterns[0].occurrence_count == 10


class TestListSuccessfulPaths:
    @pytest.mark.asyncio
    async def test_list_returns_entities(self) -> None:
        factory, session = _mock_session_factory()
        model = FractalSuccessfulPathModel(
            id=uuid.uuid4(),
            goal_fragment="sort",
            node_descriptions=["a", "b"],
            nesting_level=0,
            total_cost_usd=Decimal("0.05"),
            usage_count=7,
            first_used=datetime(2026, 1, 1),
            last_used=datetime(2026, 3, 1),
        )
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [model]
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgFractalLearningRepository(factory)
        paths = await repo.list_successful_paths(limit=10)

        assert len(paths) == 1
        assert paths[0].goal_fragment == "sort"
        assert paths[0].usage_count == 7
        assert paths[0].total_cost_usd == pytest.approx(0.05)


# ═══════════════════════════════════════════════════════════════
# find_* tests
# ═══════════════════════════════════════════════════════════════


class TestFindErrorPatterns:
    @pytest.mark.asyncio
    async def test_find_executes_query(self) -> None:
        factory, session = _mock_session_factory()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgFractalLearningRepository(factory)
        result = await repo.find_error_patterns("implement fibonacci", "generate sequence")

        assert result == []
        session.execute.assert_awaited_once()


class TestFindSuccessfulPaths:
    @pytest.mark.asyncio
    async def test_find_executes_query(self) -> None:
        factory, session = _mock_session_factory()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        repo = PgFractalLearningRepository(factory)
        result = await repo.find_successful_paths("implement sorting")

        assert result == []
        session.execute.assert_awaited_once()

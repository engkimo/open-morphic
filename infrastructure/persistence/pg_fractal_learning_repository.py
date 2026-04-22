"""PostgreSQL FractalLearningRepository — maps ErrorPattern/SuccessfulPath <-> ORM.

Sprint 16.2: Persistent learning data storage for the Fractal Engine.
Follows the same session_factory pattern as pg_cost_repository.py.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from domain.entities.fractal_learning import ErrorPattern, SuccessfulPath
from domain.ports.fractal_learning_repository import FractalLearningRepository
from infrastructure.persistence.models import (
    FractalErrorPatternModel,
    FractalSuccessfulPathModel,
)


class PgFractalLearningRepository(FractalLearningRepository):
    """PostgreSQL-backed repository for fractal learning data."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ── Mapping helpers ──

    @staticmethod
    def _to_error_model(pattern: ErrorPattern) -> FractalErrorPatternModel:
        return FractalErrorPatternModel(
            goal_fragment=pattern.goal_fragment,
            node_description=pattern.node_description,
            error_message=pattern.error_message,
            nesting_level=pattern.nesting_level,
            occurrence_count=pattern.occurrence_count,
            first_seen=pattern.first_seen,
            last_seen=pattern.last_seen,
        )

    @staticmethod
    def _to_error_entity(model: FractalErrorPatternModel) -> ErrorPattern:
        return ErrorPattern(
            id=str(model.id)[:8],
            goal_fragment=model.goal_fragment,
            node_description=model.node_description,
            error_message=model.error_message,
            nesting_level=model.nesting_level,
            occurrence_count=model.occurrence_count,
            first_seen=model.first_seen,
            last_seen=model.last_seen,
        )

    @staticmethod
    def _to_path_model(path: SuccessfulPath) -> FractalSuccessfulPathModel:
        return FractalSuccessfulPathModel(
            goal_fragment=path.goal_fragment,
            node_descriptions=path.node_descriptions,
            nesting_level=path.nesting_level,
            total_cost_usd=Decimal(str(path.total_cost_usd)),
            usage_count=path.usage_count,
            first_used=path.first_used,
            last_used=path.last_used,
        )

    @staticmethod
    def _to_path_entity(model: FractalSuccessfulPathModel) -> SuccessfulPath:
        return SuccessfulPath(
            id=str(model.id)[:8],
            goal_fragment=model.goal_fragment,
            node_descriptions=model.node_descriptions,
            nesting_level=model.nesting_level,
            total_cost_usd=float(model.total_cost_usd),
            usage_count=model.usage_count,
            first_used=model.first_used,
            last_used=model.last_used,
        )

    # ── Error patterns ──

    async def save_error_pattern(self, pattern: ErrorPattern) -> None:
        async with self._session_factory() as session:
            # Check for existing match on 3-column dedup key
            stmt = select(FractalErrorPatternModel).where(
                FractalErrorPatternModel.goal_fragment == pattern.goal_fragment,
                FractalErrorPatternModel.node_description == pattern.node_description,
                FractalErrorPatternModel.error_message == pattern.error_message,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing is not None:
                existing.occurrence_count += 1
                existing.last_seen = datetime.now()
            else:
                session.add(self._to_error_model(pattern))

            await session.commit()

    async def find_error_patterns(self, goal: str, node_desc: str) -> list[ErrorPattern]:
        async with self._session_factory() as session:
            # Domain matches(): goal_fragment IN goal AND node_description IN node_desc
            # In PG: strpos(lower(goal), lower(goal_fragment)) > 0
            goal_lower = goal.lower()
            node_lower = node_desc.lower()
            stmt = select(FractalErrorPatternModel).where(
                func.strpos(goal_lower, func.lower(FractalErrorPatternModel.goal_fragment)) > 0,
                func.strpos(node_lower, func.lower(FractalErrorPatternModel.node_description)) > 0,
            )
            result = await session.execute(stmt)
            return [self._to_error_entity(row) for row in result.scalars().all()]

    async def find_error_patterns_by_goal(self, goal: str) -> list[ErrorPattern]:
        async with self._session_factory() as session:
            # Fetch all patterns and filter with n-gram overlap in Python.
            # The learning dataset is small (hundreds), so this is efficient
            # and avoids SQL substring-only matching that fails on rephrased
            # goals and CJK text.
            stmt = select(FractalErrorPatternModel)
            result = await session.execute(stmt)
            all_patterns = [self._to_error_entity(row) for row in result.scalars().all()]
            return [p for p in all_patterns if p.matches_goal(goal)]

    async def list_error_patterns(self, limit: int = 50) -> list[ErrorPattern]:
        async with self._session_factory() as session:
            stmt = (
                select(FractalErrorPatternModel)
                .order_by(FractalErrorPatternModel.occurrence_count.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [self._to_error_entity(row) for row in result.scalars().all()]

    # ── Successful paths ──

    async def save_successful_path(self, path: SuccessfulPath) -> None:
        async with self._session_factory() as session:
            # Check for existing match on goal_fragment + node_descriptions JSONB
            stmt = select(FractalSuccessfulPathModel).where(
                FractalSuccessfulPathModel.goal_fragment == path.goal_fragment,
                FractalSuccessfulPathModel.node_descriptions == path.node_descriptions,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing is not None:
                existing.usage_count += 1
                existing.last_used = datetime.now()
                # Keep the lower cost
                new_cost = Decimal(str(path.total_cost_usd))
                if new_cost < existing.total_cost_usd:
                    existing.total_cost_usd = new_cost
            else:
                session.add(self._to_path_model(path))

            await session.commit()

    async def find_successful_paths(self, goal: str) -> list[SuccessfulPath]:
        async with self._session_factory() as session:
            stmt = select(FractalSuccessfulPathModel)
            result = await session.execute(stmt)
            all_paths = [self._to_path_entity(row) for row in result.scalars().all()]
            return [p for p in all_paths if p.matches_goal(goal)]

    async def list_successful_paths(self, limit: int = 50) -> list[SuccessfulPath]:
        async with self._session_factory() as session:
            stmt = (
                select(FractalSuccessfulPathModel)
                .order_by(FractalSuccessfulPathModel.usage_count.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [self._to_path_entity(row) for row in result.scalars().all()]

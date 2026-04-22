"""PostgreSQL AgentAffinityRepository — maps AgentAffinityScore <-> ORM.

Sprint 17.1: Persistent affinity scores for engine-topic routing.
Follows the same session_factory pattern as pg_fractal_learning_repository.py.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from domain.entities.cognitive import AgentAffinityScore
from domain.ports.agent_affinity_repository import AgentAffinityRepository
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.persistence.models import AgentAffinityScoreModel


class PgAgentAffinityRepository(AgentAffinityRepository):
    """PostgreSQL-backed repository for agent affinity scores."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ── Mapping helpers ──

    @staticmethod
    def _to_model(score: AgentAffinityScore) -> AgentAffinityScoreModel:
        return AgentAffinityScoreModel(
            engine=score.engine.value,
            topic=score.topic,
            familiarity=score.familiarity,
            recency=score.recency,
            success_rate=score.success_rate,
            cost_efficiency=score.cost_efficiency,
            sample_count=score.sample_count,
            last_used=score.last_used,
        )

    @staticmethod
    def _to_entity(model: AgentAffinityScoreModel) -> AgentAffinityScore:
        return AgentAffinityScore(
            engine=AgentEngineType(model.engine),
            topic=model.topic,
            familiarity=model.familiarity,
            recency=model.recency,
            success_rate=model.success_rate,
            cost_efficiency=model.cost_efficiency,
            sample_count=model.sample_count,
            last_used=model.last_used,
        )

    # ── Port methods ──

    async def get(self, engine: AgentEngineType, topic: str) -> AgentAffinityScore | None:
        async with self._session_factory() as session:
            stmt = select(AgentAffinityScoreModel).where(
                AgentAffinityScoreModel.engine == engine.value,
                AgentAffinityScoreModel.topic == topic,
            )
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            return self._to_entity(model) if model else None

    async def get_by_topic(self, topic: str) -> list[AgentAffinityScore]:
        async with self._session_factory() as session:
            stmt = select(AgentAffinityScoreModel).where(
                AgentAffinityScoreModel.topic == topic,
            )
            result = await session.execute(stmt)
            return [self._to_entity(row) for row in result.scalars().all()]

    async def get_by_engine(self, engine: AgentEngineType) -> list[AgentAffinityScore]:
        async with self._session_factory() as session:
            stmt = select(AgentAffinityScoreModel).where(
                AgentAffinityScoreModel.engine == engine.value,
            )
            result = await session.execute(stmt)
            return [self._to_entity(row) for row in result.scalars().all()]

    async def upsert(self, score: AgentAffinityScore) -> None:
        async with self._session_factory() as session:
            stmt = select(AgentAffinityScoreModel).where(
                AgentAffinityScoreModel.engine == score.engine.value,
                AgentAffinityScoreModel.topic == score.topic,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing is not None:
                existing.familiarity = score.familiarity
                existing.recency = score.recency
                existing.success_rate = score.success_rate
                existing.cost_efficiency = score.cost_efficiency
                existing.sample_count = score.sample_count
                existing.last_used = score.last_used
            else:
                session.add(self._to_model(score))

            await session.commit()

    async def list_all(self) -> list[AgentAffinityScore]:
        async with self._session_factory() as session:
            stmt = select(AgentAffinityScoreModel)
            result = await session.execute(stmt)
            return [self._to_entity(row) for row in result.scalars().all()]

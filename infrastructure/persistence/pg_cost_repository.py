"""PostgreSQL CostRepository — maps CostRecord <-> CostLogModel."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from domain.entities.cost import CostRecord
from domain.ports.cost_repository import CostRepository
from infrastructure.persistence.models import CostLogModel


class PgCostRepository(CostRepository):
    """Production-grade PostgreSQL repository for cost records."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _to_model(record: CostRecord) -> CostLogModel:
        return CostLogModel(
            model=record.model,
            prompt_tokens=record.prompt_tokens,
            completion_tokens=record.completion_tokens,
            cost_usd=Decimal(str(record.cost_usd)),
            cached_tokens=record.cached_tokens,
            is_local=record.is_local,
            created_at=record.timestamp,
        )

    @staticmethod
    def _to_entity(model: CostLogModel) -> CostRecord:
        return CostRecord(
            model=model.model,
            prompt_tokens=model.prompt_tokens,
            completion_tokens=model.completion_tokens,
            cost_usd=float(model.cost_usd),
            cached_tokens=model.cached_tokens,
            is_local=model.is_local,
            timestamp=model.created_at,
        )

    async def save(self, record: CostRecord) -> None:
        async with self._session_factory() as session:
            session.add(self._to_model(record))
            await session.commit()

    async def get_daily_total(self) -> float:
        async with self._session_factory() as session:
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            stmt = select(func.coalesce(func.sum(CostLogModel.cost_usd), 0)).where(
                CostLogModel.created_at >= today_start
            )
            result = await session.execute(stmt)
            return float(result.scalar_one())

    async def get_monthly_total(self) -> float:
        async with self._session_factory() as session:
            month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            stmt = select(func.coalesce(func.sum(CostLogModel.cost_usd), 0)).where(
                CostLogModel.created_at >= month_start
            )
            result = await session.execute(stmt)
            return float(result.scalar_one())

    async def get_local_usage_rate(self) -> float:
        async with self._session_factory() as session:
            total_stmt = select(func.count()).select_from(CostLogModel)
            total = (await session.execute(total_stmt)).scalar_one()
            if total == 0:
                return 0.0
            local_stmt = select(func.count()).select_from(CostLogModel).where(
                CostLogModel.is_local.is_(True)
            )
            local = (await session.execute(local_stmt)).scalar_one()
            return local / total

    async def list_recent(self, limit: int = 50) -> list[CostRecord]:
        async with self._session_factory() as session:
            stmt = (
                select(CostLogModel)
                .order_by(CostLogModel.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [self._to_entity(row) for row in result.scalars().all()]

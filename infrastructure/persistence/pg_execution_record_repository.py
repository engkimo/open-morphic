"""PostgreSQL ExecutionRecordRepository — maps ExecutionRecord <-> ORM.

Sprint 17.1: Persistent execution history for Self-Evolution Engine.
Follows the same session_factory pattern as pg_fractal_learning_repository.py.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from domain.entities.execution_record import ExecutionRecord
from domain.ports.execution_record_repository import (
    ExecutionRecordRepository,
    ExecutionStats,
)
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from infrastructure.persistence.models import ExecutionRecordModel


class PgExecutionRecordRepository(ExecutionRecordRepository):
    """PostgreSQL-backed repository for execution records."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ── Mapping helpers ──

    @staticmethod
    def _to_model(record: ExecutionRecord) -> ExecutionRecordModel:
        return ExecutionRecordModel(
            task_id=record.task_id,
            task_type=record.task_type.value,
            goal=record.goal,
            engine_used=record.engine_used.value,
            model_used=record.model_used,
            success=record.success,
            error_message=record.error_message,
            cost_usd=Decimal(str(record.cost_usd)),
            duration_seconds=record.duration_seconds,
            cache_hit_rate=record.cache_hit_rate,
            user_rating=record.user_rating,
            created_at=record.created_at,
        )

    @staticmethod
    def _to_entity(model: ExecutionRecordModel) -> ExecutionRecord:
        return ExecutionRecord(
            id=str(model.id),
            task_id=model.task_id,
            task_type=TaskType(model.task_type),
            goal=model.goal,
            engine_used=AgentEngineType(model.engine_used),
            model_used=model.model_used,
            success=model.success,
            error_message=model.error_message,
            cost_usd=float(model.cost_usd),
            duration_seconds=model.duration_seconds,
            cache_hit_rate=model.cache_hit_rate,
            user_rating=model.user_rating,
            created_at=model.created_at,
        )

    # ── Port methods ──

    async def save(self, record: ExecutionRecord) -> None:
        async with self._session_factory() as session:
            session.add(self._to_model(record))
            await session.commit()

    async def list_recent(self, limit: int = 100) -> list[ExecutionRecord]:
        async with self._session_factory() as session:
            stmt = (
                select(ExecutionRecordModel)
                .order_by(ExecutionRecordModel.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [self._to_entity(row) for row in result.scalars().all()]

    async def list_by_task_type(
        self, task_type: TaskType, limit: int = 50
    ) -> list[ExecutionRecord]:
        async with self._session_factory() as session:
            stmt = (
                select(ExecutionRecordModel)
                .where(ExecutionRecordModel.task_type == task_type.value)
                .order_by(ExecutionRecordModel.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [self._to_entity(row) for row in result.scalars().all()]

    async def list_failures(self, since: datetime | None = None) -> list[ExecutionRecord]:
        async with self._session_factory() as session:
            stmt = select(ExecutionRecordModel).where(ExecutionRecordModel.success.is_(False))
            if since is not None:
                stmt = stmt.where(ExecutionRecordModel.created_at >= since)
            stmt = stmt.order_by(ExecutionRecordModel.created_at.desc())
            result = await session.execute(stmt)
            return [self._to_entity(row) for row in result.scalars().all()]

    async def get_stats(self, task_type: TaskType | None = None) -> ExecutionStats:
        async with self._session_factory() as session:
            base = select(ExecutionRecordModel)
            if task_type is not None:
                base = base.where(ExecutionRecordModel.task_type == task_type.value)

            # Aggregation query
            agg_stmt = select(
                func.count().label("total"),
                func.sum(case((ExecutionRecordModel.success.is_(True), 1), else_=0)).label(
                    "success_count"
                ),
                func.avg(ExecutionRecordModel.cost_usd).label("avg_cost"),
                func.avg(ExecutionRecordModel.duration_seconds).label("avg_duration"),
            ).select_from(base.subquery())

            agg_result = await session.execute(agg_stmt)
            row = agg_result.one()
            total = row.total or 0
            if total == 0:
                return ExecutionStats()

            # Distribution queries
            model_stmt = select(
                ExecutionRecordModel.model_used,
                func.count().label("cnt"),
            ).where(ExecutionRecordModel.model_used != "")
            engine_stmt = select(
                ExecutionRecordModel.engine_used,
                func.count().label("cnt"),
            )
            if task_type is not None:
                model_stmt = model_stmt.where(ExecutionRecordModel.task_type == task_type.value)
                engine_stmt = engine_stmt.where(ExecutionRecordModel.task_type == task_type.value)
            model_stmt = model_stmt.group_by(ExecutionRecordModel.model_used)
            engine_stmt = engine_stmt.group_by(ExecutionRecordModel.engine_used)

            model_result = await session.execute(model_stmt)
            engine_result = await session.execute(engine_stmt)

            model_dist = {r.model_used: r.cnt for r in model_result}
            engine_dist = {r.engine_used: r.cnt for r in engine_result}

            return ExecutionStats(
                total_count=total,
                success_count=row.success_count or 0,
                failure_count=total - (row.success_count or 0),
                avg_cost_usd=float(row.avg_cost or 0),
                avg_duration_seconds=float(row.avg_duration or 0),
                model_distribution=model_dist,
                engine_distribution=engine_dist,
            )

"""PostgreSQL SharedTaskStateRepository — maps SharedTaskState <-> ORM.

Sprint 17.1: Persistent cross-agent task state for UCL.
Follows the same session_factory pattern as pg_fractal_learning_repository.py.

Design: decisions and agent_history are stored as JSONB arrays.
Pydantic model_dump(mode="json") serialises them; model_validate() restores.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from domain.entities.cognitive import AgentAction, Decision, SharedTaskState
from domain.ports.shared_task_state_repository import SharedTaskStateRepository
from infrastructure.persistence.models import SharedTaskStateModel

_RECENT_HOURS = 24


class PgSharedTaskStateRepository(SharedTaskStateRepository):
    """PostgreSQL-backed repository for shared task state."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ── Mapping helpers ──

    @staticmethod
    def _to_model(state: SharedTaskState) -> SharedTaskStateModel:
        return SharedTaskStateModel(
            task_id=state.task_id,
            decisions=[d.model_dump(mode="json") for d in state.decisions],
            artifacts=state.artifacts,
            blockers=state.blockers,
            agent_history=[a.model_dump(mode="json") for a in state.agent_history],
            created_at=state.created_at,
            updated_at=state.updated_at,
        )

    @staticmethod
    def _to_entity(model: SharedTaskStateModel) -> SharedTaskState:
        return SharedTaskState(
            task_id=model.task_id,
            decisions=[Decision.model_validate(d, strict=False) for d in (model.decisions or [])],
            artifacts=model.artifacts or {},
            blockers=model.blockers or [],
            agent_history=[
                AgentAction.model_validate(a, strict=False) for a in (model.agent_history or [])
            ],
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    # ── Port methods ──

    async def save(self, state: SharedTaskState) -> None:
        async with self._session_factory() as session:
            stmt = select(SharedTaskStateModel).where(
                SharedTaskStateModel.task_id == state.task_id,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing is not None:
                existing.decisions = [d.model_dump(mode="json") for d in state.decisions]
                existing.artifacts = state.artifacts
                existing.blockers = state.blockers
                existing.agent_history = [a.model_dump(mode="json") for a in state.agent_history]
                existing.updated_at = state.updated_at
            else:
                session.add(self._to_model(state))

            await session.commit()

    async def get(self, task_id: str) -> SharedTaskState | None:
        async with self._session_factory() as session:
            stmt = select(SharedTaskStateModel).where(
                SharedTaskStateModel.task_id == task_id,
            )
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            return self._to_entity(model) if model else None

    async def list_active(self) -> list[SharedTaskState]:
        async with self._session_factory() as session:
            cutoff = datetime.now(tz=UTC) - timedelta(hours=_RECENT_HOURS)
            # Active = has blockers (non-empty JSONB array) OR recently updated
            stmt = (
                select(SharedTaskStateModel)
                .where(
                    (SharedTaskStateModel.blockers != [])  # noqa: E712 — JSONB comparison
                    | (SharedTaskStateModel.updated_at >= cutoff)
                )
                .order_by(SharedTaskStateModel.updated_at.desc())
            )
            result = await session.execute(stmt)
            return [self._to_entity(row) for row in result.scalars().all()]

    async def update_decisions(self, state: SharedTaskState) -> None:
        async with self._session_factory() as session:
            stmt = select(SharedTaskStateModel).where(
                SharedTaskStateModel.task_id == state.task_id,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is None:
                return
            existing.decisions = [d.model_dump(mode="json") for d in state.decisions]
            existing.updated_at = datetime.now(tz=UTC)
            await session.commit()

    async def update_artifacts(self, state: SharedTaskState) -> None:
        async with self._session_factory() as session:
            stmt = select(SharedTaskStateModel).where(
                SharedTaskStateModel.task_id == state.task_id,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is None:
                return
            existing.artifacts = state.artifacts
            existing.updated_at = datetime.now(tz=UTC)
            await session.commit()

    async def append_action(self, task_id: str, action: AgentAction) -> None:
        async with self._session_factory() as session:
            stmt = select(SharedTaskStateModel).where(
                SharedTaskStateModel.task_id == task_id,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is None:
                return
            history = list(existing.agent_history or [])
            history.append(action.model_dump(mode="json"))
            existing.agent_history = history
            existing.updated_at = datetime.now(tz=UTC)
            await session.commit()

    async def delete(self, task_id: str) -> None:
        async with self._session_factory() as session:
            stmt = select(SharedTaskStateModel).where(
                SharedTaskStateModel.task_id == task_id,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is not None:
                await session.delete(existing)
                await session.commit()

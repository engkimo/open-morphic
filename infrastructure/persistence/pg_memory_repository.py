"""PostgreSQL MemoryRepository — maps MemoryEntry <-> MemoryModel with keyword search."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from domain.entities.memory import MemoryEntry
from domain.ports.memory_repository import MemoryRepository
from domain.value_objects.status import MemoryType
from infrastructure.persistence.models import MemoryModel


class PgMemoryRepository(MemoryRepository):
    """PostgreSQL repository for memory entries. Keyword search (embedding deferred)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _to_model(entry: MemoryEntry) -> MemoryModel:
        return MemoryModel(
            id=uuid.UUID(entry.id) if len(entry.id) == 36 else uuid.uuid5(uuid.NAMESPACE_DNS, entry.id),
            content=entry.content,
            memory_type=entry.memory_type.value,
            access_count=entry.access_count,
            importance_score=entry.importance_score,
            metadata_=entry.metadata,
            created_at=entry.created_at,
            last_accessed=entry.last_accessed,
        )

    @staticmethod
    def _to_entity(model: MemoryModel) -> MemoryEntry:
        return MemoryEntry(
            id=str(model.id),
            content=model.content,
            memory_type=MemoryType(model.memory_type),
            access_count=model.access_count,
            importance_score=model.importance_score,
            metadata=model.metadata_ or {},
            created_at=model.created_at,
            last_accessed=model.last_accessed,
        )

    async def add(self, entry: MemoryEntry) -> None:
        async with self._session_factory() as session:
            session.add(self._to_model(entry))
            await session.commit()

    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """Keyword-based search using SQL ILIKE. Embedding search deferred to Phase 3."""
        async with self._session_factory() as session:
            words = query.strip().split()
            if not words:
                return []
            # Search for entries containing any query word
            conditions = [MemoryModel.content.ilike(f"%{w}%") for w in words]
            # OR-match: any word
            from sqlalchemy import or_

            stmt = (
                select(MemoryModel)
                .where(or_(*conditions))
                .order_by(MemoryModel.last_accessed.desc())
                .limit(top_k)
            )
            result = await session.execute(stmt)
            return [self._to_entity(row) for row in result.scalars().all()]

    async def get_by_id(self, memory_id: str) -> MemoryEntry | None:
        async with self._session_factory() as session:
            try:
                uid = uuid.UUID(memory_id)
            except ValueError:
                return None
            model = await session.get(MemoryModel, uid)
            if model is None:
                return None
            return self._to_entity(model)

    async def delete(self, memory_id: str) -> None:
        async with self._session_factory() as session:
            try:
                uid = uuid.UUID(memory_id)
            except ValueError:
                return
            model = await session.get(MemoryModel, uid)
            if model is not None:
                await session.delete(model)
                await session.commit()

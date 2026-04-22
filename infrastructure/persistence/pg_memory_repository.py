"""PostgreSQL MemoryRepository — maps MemoryEntry <-> MemoryModel.

Supports optional embedding-based vector search via pgvector cosine distance.
Falls back to keyword ILIKE search when no embedding_port is provided.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from domain.entities.memory import MemoryEntry
from domain.ports.embedding import EmbeddingPort
from domain.ports.memory_repository import MemoryRepository
from domain.value_objects.status import MemoryType
from infrastructure.persistence.models import MemoryModel

logger = logging.getLogger(__name__)


class PgMemoryRepository(MemoryRepository):
    """PostgreSQL repository for memory entries with optional vector search."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embedding_port: EmbeddingPort | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._embedding_port = embedding_port

    @staticmethod
    def _to_model(entry: MemoryEntry) -> MemoryModel:
        return MemoryModel(
            id=(
                uuid.UUID(entry.id)
                if len(entry.id) == 36
                else uuid.uuid5(uuid.NAMESPACE_DNS, entry.id)
            ),
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
            model = self._to_model(entry)
            # Generate and store embedding if port is available
            if self._embedding_port is not None and MemoryModel.embedding is not None:
                try:
                    vectors = await self._embedding_port.embed([entry.content])
                    if vectors:
                        model.embedding = vectors[0]
                except Exception:
                    logger.debug("Embedding failed for entry %s", entry.id)
            session.add(model)
            await session.commit()

    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """Vector search when embedding_port available, else keyword ILIKE fallback."""
        if self._embedding_port is not None and MemoryModel.embedding is not None:
            return await self._vector_search(query, top_k)
        return await self._keyword_search(query, top_k)

    async def _keyword_search(self, query: str, top_k: int) -> list[MemoryEntry]:
        """Keyword-based search using SQL ILIKE."""
        async with self._session_factory() as session:
            words = query.strip().split()
            if not words:
                return []
            conditions = [MemoryModel.content.ilike(f"%{w}%") for w in words]
            from sqlalchemy import or_

            stmt = (
                select(MemoryModel)
                .where(or_(*conditions))
                .order_by(MemoryModel.last_accessed.desc())
                .limit(top_k)
            )
            result = await session.execute(stmt)
            return [self._to_entity(row) for row in result.scalars().all()]

    async def _vector_search(self, query: str, top_k: int) -> list[MemoryEntry]:
        """pgvector cosine distance search."""
        try:
            vectors = await self._embedding_port.embed([query])  # type: ignore[union-attr]
            if not vectors:
                return await self._keyword_search(query, top_k)
        except Exception:
            logger.debug("Query embedding failed, falling back to keyword search")
            return await self._keyword_search(query, top_k)

        query_vec = vectors[0]
        async with self._session_factory() as session:
            # pgvector cosine_distance: ORDER BY embedding <=> query_vec ASC
            stmt = (
                select(MemoryModel)
                .where(MemoryModel.embedding.isnot(None))
                .order_by(MemoryModel.embedding.cosine_distance(query_vec))
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

    async def list_by_type(self, memory_type: MemoryType, limit: int = 100) -> list[MemoryEntry]:
        async with self._session_factory() as session:
            stmt = (
                select(MemoryModel)
                .where(MemoryModel.memory_type == memory_type.value)
                .order_by(MemoryModel.last_accessed.asc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [self._to_entity(row) for row in result.scalars().all()]

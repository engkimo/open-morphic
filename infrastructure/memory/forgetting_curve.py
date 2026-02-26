"""ForgettingCurveManager — async manager for L2 memory expiration.

Scans L2 entries, computes retention scores via domain ForgettingCurve,
promotes expired entries to L3 Knowledge Graph (if available), then deletes them.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.entities.memory import MemoryEntry
from domain.ports.knowledge_graph import KnowledgeGraphPort
from domain.ports.memory_repository import MemoryRepository
from domain.services.forgetting_curve import ForgettingCurve
from domain.value_objects.status import MemoryType


@dataclass(frozen=True)
class CompactResult:
    """Statistics from a compact() run."""

    scanned: int
    expired: int
    promoted: int
    deleted: int


class ForgettingCurveManager:
    """Async manager that expires stale L2 memories.

    Uses domain ForgettingCurve for retention scoring (pure math).
    Promotes expired entries to L3 KnowledgeGraph when available.
    """

    def __init__(
        self,
        memory_repo: MemoryRepository,
        knowledge_graph: KnowledgeGraphPort | None = None,
        threshold: float = 0.3,
    ) -> None:
        self._memory_repo = memory_repo
        self._knowledge_graph = knowledge_graph
        self._threshold = threshold

    async def compact(self) -> CompactResult:
        """Scan L2 entries, expire stale ones, promote to L3, delete from L2."""
        entries = await self._memory_repo.list_by_type(MemoryType.L2_SEMANTIC)
        scanned = len(entries)
        expired = 0
        promoted = 0
        deleted = 0

        for entry in entries:
            hours = ForgettingCurve.hours_since(entry.last_accessed)
            if ForgettingCurve.is_expired(
                access_count=entry.access_count,
                importance_score=entry.importance_score,
                hours_elapsed=hours,
                threshold=self._threshold,
            ):
                expired += 1
                entity_id = await self._promote_to_facts(entry)
                if entity_id is not None:
                    promoted += 1
                await self._memory_repo.delete(entry.id)
                deleted += 1

        return CompactResult(
            scanned=scanned,
            expired=expired,
            promoted=promoted,
            deleted=deleted,
        )

    async def _promote_to_facts(self, entry: MemoryEntry) -> str | None:
        """Store as KG entity type='memory_fact'. Returns entity_id or None."""
        if self._knowledge_graph is None:
            return None
        return await self._knowledge_graph.add_entity(
            name=entry.content,
            entity_type="memory_fact",
            properties={
                "source_id": entry.id,
                "access_count": entry.access_count,
                "importance_score": entry.importance_score,
            },
        )

    def score_entry(self, entry: MemoryEntry) -> float:
        """Convenience: compute retention_score for a MemoryEntry."""
        hours = ForgettingCurve.hours_since(entry.last_accessed)
        return ForgettingCurve.retention_score(
            access_count=entry.access_count,
            importance_score=entry.importance_score,
            hours_elapsed=hours,
        )

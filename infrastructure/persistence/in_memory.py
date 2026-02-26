"""In-memory repository implementations — Phase 1 production backend.

No database required. Suitable for single-process development and testing.
"""

from __future__ import annotations

import logging

from domain.entities.cost import CostRecord
from domain.entities.memory import MemoryEntry
from domain.entities.plan import ExecutionPlan
from domain.entities.task import TaskEntity
from domain.ports.cost_repository import CostRepository
from domain.ports.embedding import EmbeddingPort
from domain.ports.memory_repository import MemoryRepository
from domain.ports.plan_repository import PlanRepository
from domain.ports.task_repository import TaskRepository
from domain.value_objects.status import TaskStatus

logger = logging.getLogger(__name__)


class InMemoryTaskRepository(TaskRepository):
    """Dict-backed TaskRepository."""

    def __init__(self) -> None:
        self._store: dict[str, TaskEntity] = {}

    async def save(self, task: TaskEntity) -> None:
        self._store[task.id] = task

    async def get_by_id(self, task_id: str) -> TaskEntity | None:
        return self._store.get(task_id)

    async def list_all(self) -> list[TaskEntity]:
        return sorted(self._store.values(), key=lambda t: t.created_at, reverse=True)

    async def list_by_status(self, status: TaskStatus) -> list[TaskEntity]:
        return [t for t in self._store.values() if t.status == status]

    async def update(self, task: TaskEntity) -> None:
        self._store[task.id] = task

    async def delete(self, task_id: str) -> None:
        self._store.pop(task_id, None)


class InMemoryCostRepository(CostRepository):
    """List-backed CostRepository."""

    def __init__(self) -> None:
        self._records: list[CostRecord] = []

    @property
    def records(self) -> list[CostRecord]:
        return self._records

    async def save(self, record: CostRecord) -> None:
        self._records.append(record)

    async def get_daily_total(self) -> float:
        return sum(r.cost_usd for r in self._records)

    async def get_monthly_total(self) -> float:
        return sum(r.cost_usd for r in self._records)

    async def get_local_usage_rate(self) -> float:
        if not self._records:
            return 0.0
        local = sum(1 for r in self._records if r.is_local)
        return local / len(self._records)

    async def list_recent(self, limit: int = 50) -> list[CostRecord]:
        return sorted(self._records, key=lambda r: r.timestamp, reverse=True)[:limit]


class InMemoryMemoryRepository(MemoryRepository):
    """Dict-backed MemoryRepository with optional embedding-based vector search.

    When embedding_port is provided: uses SemanticBucketStore for vector similarity.
    When embedding_port is None: falls back to keyword overlap (backward compat).
    """

    def __init__(self, embedding_port: EmbeddingPort | None = None) -> None:
        self._store: dict[str, MemoryEntry] = {}
        self._embedding_port = embedding_port
        self._bucket_store: SemanticBucketStore | None = None
        if embedding_port is not None:
            from domain.services.semantic_fingerprint import SemanticFingerprint
            from infrastructure.memory.semantic_fingerprint import SemanticBucketStore

            fp = SemanticFingerprint(dimensions=embedding_port.dimensions())
            self._bucket_store = SemanticBucketStore(fingerprint=fp)

    async def add(self, entry: MemoryEntry) -> None:
        self._store[entry.id] = entry
        if self._embedding_port is not None and self._bucket_store is not None:
            try:
                vectors = await self._embedding_port.embed([entry.content])
                if vectors:
                    self._bucket_store.add(entry.id, vectors[0])
            except Exception:
                logger.debug("Embedding failed for entry %s, keyword fallback", entry.id)

    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        if self._embedding_port is not None and self._bucket_store is not None:
            return await self._vector_search(query, top_k)
        return self._keyword_search(query, top_k)

    async def get_by_id(self, memory_id: str) -> MemoryEntry | None:
        return self._store.get(memory_id)

    async def delete(self, memory_id: str) -> None:
        self._store.pop(memory_id, None)
        if self._bucket_store is not None:
            self._bucket_store.remove(memory_id)

    def _keyword_search(self, query: str, top_k: int) -> list[MemoryEntry]:
        """Original keyword overlap search (backward compat)."""
        query_lower = query.lower()
        query_words = set(query_lower.split())
        scored: list[tuple[float, MemoryEntry]] = []
        for entry in self._store.values():
            words = set(entry.content.lower().split())
            overlap = len(words & query_words)
            if overlap > 0:
                scored.append((float(overlap), entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]

    async def _vector_search(self, query: str, top_k: int) -> list[MemoryEntry]:
        """Embedding-based vector similarity search via SemanticBucketStore."""
        try:
            vectors = await self._embedding_port.embed([query])  # type: ignore[union-attr]
            if not vectors:
                return self._keyword_search(query, top_k)
        except Exception:
            logger.debug("Query embedding failed, falling back to keyword search")
            return self._keyword_search(query, top_k)

        similar = self._bucket_store.find_similar(  # type: ignore[union-attr]
            vectors[0], top_k=top_k, threshold=0.0, multi_probe_bits=2
        )
        results: list[MemoryEntry] = []
        for entry_id, _sim in similar:
            entry = self._store.get(entry_id)
            if entry is not None:
                results.append(entry)
        return results


class InMemoryPlanRepository(PlanRepository):
    """Dict-backed PlanRepository."""

    def __init__(self) -> None:
        self._store: dict[str, ExecutionPlan] = {}

    async def save(self, plan: ExecutionPlan) -> None:
        self._store[plan.id] = plan

    async def get_by_id(self, plan_id: str) -> ExecutionPlan | None:
        return self._store.get(plan_id)

    async def list_all(self) -> list[ExecutionPlan]:
        return sorted(self._store.values(), key=lambda p: p.created_at, reverse=True)

    async def update(self, plan: ExecutionPlan) -> None:
        self._store[plan.id] = plan

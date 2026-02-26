"""MemoryHierarchy — L1-L4 unified memory manager.

CPU-cache-inspired design:
  L1: Active Context — in-memory deque (fastest, smallest)
  L2: Semantic Cache — vector similarity via MemoryRepository
  L3: Structured Facts — entity-relation via KnowledgeGraphPort
  L4: Cold Storage — full-text search via MemoryRepository (slowest, largest)
"""

from __future__ import annotations

import collections
from typing import Any

from domain.entities.memory import MemoryEntry
from domain.ports.knowledge_graph import KnowledgeGraphPort
from domain.ports.memory_repository import MemoryRepository
from domain.value_objects.status import MemoryType
from infrastructure.memory.forgetting_curve import ForgettingCurveManager


def _estimate_tokens(text: str) -> int:
    """Approximate token count: ~4 chars per token."""
    return max(1, len(text) // 4)


class MemoryHierarchy:
    """Unified L1-L4 memory manager.

    L1: in-memory deque (bounded, O(1) append/pop)
    L2: semantic similarity search via MemoryRepository
    L3: structured knowledge graph (optional, gracefully degrades)
    L4: cold storage full-text search via MemoryRepository
    """

    def __init__(
        self,
        memory_repo: MemoryRepository,
        knowledge_graph: KnowledgeGraphPort | None = None,
        max_l1_entries: int = 50,
    ) -> None:
        self._memory_repo = memory_repo
        self._knowledge_graph = knowledge_graph
        self._l1: collections.deque[str] = collections.deque(maxlen=max_l1_entries)

    @property
    def l1_entries(self) -> list[str]:
        """Return current L1 entries (for testing/inspection)."""
        return list(self._l1)

    async def add(self, content: str, role: str = "user") -> None:
        """Add content to L1 (always) and L2 (persistent)."""
        self._l1.append(content)

        entry = MemoryEntry(
            content=content,
            memory_type=MemoryType.L2_SEMANTIC,
            metadata={"role": role},
        )
        await self._memory_repo.add(entry)

    async def compact(self, threshold: float = 0.3) -> dict:
        """Expire stale L2 memories. Delegates to ForgettingCurveManager.

        Returns dict with scanned/expired/promoted/deleted counts.
        """
        mgr = ForgettingCurveManager(
            memory_repo=self._memory_repo,
            knowledge_graph=self._knowledge_graph,
            threshold=threshold,
        )
        result = await mgr.compact()
        return {
            "scanned": result.scanned,
            "expired": result.expired,
            "promoted": result.promoted,
            "deleted": result.deleted,
        }

    async def retrieve(self, query: str, max_tokens: int = 500) -> str:
        """Search L1 → L2 → L3, assemble results within token budget."""
        budget = max_tokens
        results: list[str] = []

        # L1: keyword scan of in-memory deque
        budget = self._scan_l1(query, budget, results)

        # L2: semantic similarity search
        if budget > 0:
            budget = await self._scan_l2(query, budget, results)

        # L3: knowledge graph entity search (optional)
        if budget > 0 and self._knowledge_graph is not None:
            budget = await self._scan_l3(query, budget, results)

        return "\n---\n".join(results)

    def _scan_l1(self, query: str, budget: int, results: list[str]) -> int:
        """Scan L1 deque for keyword matches."""
        query_lower = query.lower()
        query_words = set(query_lower.split())

        for entry in reversed(list(self._l1)):
            if budget <= 0:
                break
            entry_lower = entry.lower()
            if query_words & set(entry_lower.split()):
                tokens = _estimate_tokens(entry)
                if tokens <= budget:
                    results.append(entry)
                    budget -= tokens
        return budget

    async def _scan_l2(self, query: str, budget: int, results: list[str]) -> int:
        """Search L2 semantic memory via repository."""
        entries = await self._memory_repo.search(query, top_k=5)
        for entry in entries:
            if budget <= 0:
                break
            if entry.content not in results:
                tokens = _estimate_tokens(entry.content)
                if tokens <= budget:
                    results.append(entry.content)
                    budget -= tokens
        return budget

    async def _scan_l3(self, query: str, budget: int, results: list[str]) -> int:
        """Search L3 knowledge graph for related entities."""
        entities = await self._knowledge_graph.search_entities(query)  # type: ignore[union-attr]
        for entity in entities:
            if budget <= 0:
                break
            text = _format_entity(entity)
            if text not in results:
                tokens = _estimate_tokens(text)
                if tokens <= budget:
                    results.append(text)
                    budget -= tokens
        return budget


def _format_entity(entity: dict[str, Any]) -> str:
    """Format a knowledge graph entity dict as a readable string."""
    name = entity.get("name", "unknown")
    etype = entity.get("entity_type", "")
    props = {k: v for k, v in entity.items() if k not in ("name", "entity_type", "id")}
    parts = [f"[{etype}] {name}" if etype else name]
    if props:
        parts.append(str(props))
    return " ".join(parts)

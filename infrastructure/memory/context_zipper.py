"""ContextZipper — query-adaptive context compression (v2).

Compresses conversation history to fit within a token budget, prioritizing
messages that are most relevant to the current query and most recent.

v2 adds:
- async compress() for embedding-based semantic scoring
- Optional ports: EmbeddingPort, MemoryRepository, KnowledgeGraphPort
- Budget allocation: [Facts] → [Memory] → [History]
- ingest() method for distributing messages to L2 memory
"""

from __future__ import annotations

from domain.entities.memory import MemoryEntry
from domain.ports.embedding import EmbeddingPort
from domain.ports.knowledge_graph import KnowledgeGraphPort
from domain.ports.memory_repository import MemoryRepository
from domain.services.semantic_fingerprint import SemanticFingerprint
from domain.value_objects.status import MemoryType


def _estimate_tokens(text: str) -> int:
    """Approximate token count: ~4 chars per token."""
    return max(1, len(text) // 4)


def _keyword_overlap(text: str, query: str) -> float:
    """Score text by keyword overlap with query (0.0-1.0)."""
    query_words = set(query.lower().split())
    if not query_words:
        return 0.0
    text_words = set(text.lower().split())
    overlap = len(query_words & text_words)
    return overlap / len(query_words)


class ContextZipper:
    """Compress conversation history to fit within a token budget.

    v2: Supports optional embedding-based semantic scoring, knowledge graph
    facts augmentation, and memory repository augmentation.

    When no ports are provided, falls back to keyword-only scoring (v1 behavior).

    Budget allocation (when all sources available):
      [Facts] (facts_budget_pct) → [Memory] (memory_budget_pct) → [History] (remainder)
    """

    def __init__(
        self,
        embedding_port: EmbeddingPort | None = None,
        memory_repo: MemoryRepository | None = None,
        knowledge_graph: KnowledgeGraphPort | None = None,
        facts_budget_pct: float = 0.20,
        memory_budget_pct: float = 0.30,
    ) -> None:
        self._embedding_port = embedding_port
        self._memory_repo = memory_repo
        self._knowledge_graph = knowledge_graph
        self._facts_budget_pct = facts_budget_pct
        self._memory_budget_pct = memory_budget_pct

    async def compress(
        self,
        history: list[str],
        query: str,
        max_tokens: int = 500,
    ) -> str:
        """Compress history + augment with memory/facts, within token budget.

        Args:
            history: List of conversation messages (oldest first).
            query: Current query — used for relevance scoring.
            max_tokens: Target token budget.

        Returns:
            Compressed context string with [Facts], [Memory], and history sections.
        """
        if not history and not self._knowledge_graph and not self._memory_repo:
            return ""

        sections: list[str] = []
        remaining_budget = max_tokens

        # Phase 1: Facts from knowledge graph (highest density per token)
        if self._knowledge_graph is not None and query:
            facts_budget = int(max_tokens * self._facts_budget_pct)
            facts_text, used = await self._collect_facts(query, facts_budget)
            if facts_text:
                sections.append(facts_text)
                remaining_budget -= used

        # Phase 2: Memories from L2 repository
        if self._memory_repo is not None and query:
            memory_budget = int(max_tokens * self._memory_budget_pct)
            memory_budget = min(memory_budget, remaining_budget)
            history_set = set(history) if history else set()
            memory_text, used = await self._collect_memories(query, memory_budget, history_set)
            if memory_text:
                sections.append(memory_text)
                remaining_budget -= used

        # Phase 3: History (scored by relevance + recency)
        if history:
            history_text = await self._compress_history(history, query, remaining_budget)
            if history_text:
                sections.append(history_text)

        return "\n---\n".join(sections)

    async def ingest(self, message: str, role: str = "user") -> None:
        """Store message to L2 memory for future retrieval.

        No-op when memory_repo is not configured.
        """
        if self._memory_repo is None:
            return
        entry = MemoryEntry(
            content=message,
            memory_type=MemoryType.L2_SEMANTIC,
            metadata={"role": role},
        )
        await self._memory_repo.add(entry)

    async def _compress_history(
        self,
        history: list[str],
        query: str,
        max_tokens: int,
    ) -> str:
        """Score and select history messages within budget."""
        if not history:
            return ""

        total_count = len(history)

        # Score messages: semantic (if available) or keyword
        if self._embedding_port is not None and query:
            scores = await self._semantic_scores(history, query)
        else:
            scores = [_keyword_overlap(msg, query) for msg in history]

        scored: list[tuple[float, int, str]] = []
        for idx, msg in enumerate(history):
            recency = (idx + 1) / total_count  # 0→1, recent = higher
            relevance = scores[idx]
            score = recency * 0.4 + relevance * 0.6
            scored.append((score, idx, msg))

        scored.sort(key=lambda x: x[0], reverse=True)

        budget = max_tokens
        selected: list[tuple[int, str]] = []

        for _score, idx, msg in scored:
            if budget <= 0:
                break
            tokens = _estimate_tokens(msg)
            separator_cost = 1 if selected else 0
            if tokens + separator_cost <= budget:
                selected.append((idx, msg))
                budget -= tokens + separator_cost

        selected.sort(key=lambda x: x[0])
        return "\n".join(msg for _, msg in selected)

    async def _semantic_scores(self, history: list[str], query: str) -> list[float]:
        """Batch-embed query + history, return cosine similarity scores."""
        all_texts = [query] + history
        embeddings = await self._embedding_port.embed(all_texts)  # type: ignore[union-attr]
        query_vec = embeddings[0]
        return [SemanticFingerprint.cosine_similarity(emb, query_vec) for emb in embeddings[1:]]

    async def _collect_facts(self, query: str, budget: int) -> tuple[str, int]:
        """Collect facts from knowledge graph, return (text, tokens_used)."""
        # Search per-word to handle multi-word queries
        seen_ids: set[str] = set()
        entities: list[dict] = []
        for word in query.split():
            if not word:
                continue
            results = await self._knowledge_graph.search_entities(word)  # type: ignore[union-attr]
            for e in results:
                eid = e.get("id", str(e))
                if eid not in seen_ids:
                    seen_ids.add(eid)
                    entities.append(e)
        if not entities:
            return "", 0

        parts: list[str] = []
        used = 0
        prefix_cost = _estimate_tokens("[Facts] ")

        for entity in entities:
            text = _format_entity(entity)
            line = f"[Facts] {text}" if not parts else text
            tokens = _estimate_tokens(line)
            extra = prefix_cost if not parts else 0
            total_cost = tokens + extra
            if used + total_cost > budget:
                break
            parts.append(line if parts else f"[Facts] {text}")
            used += tokens

        return "\n".join(parts), used

    async def _collect_memories(
        self,
        query: str,
        budget: int,
        history_set: set[str],
    ) -> tuple[str, int]:
        """Collect memories from L2 repository, return (text, tokens_used)."""
        entries = await self._memory_repo.search(query, top_k=10)  # type: ignore[union-attr]
        if not entries:
            return "", 0

        parts: list[str] = []
        used = 0

        for entry in entries:
            # Deduplicate: skip memories that are already in history
            if entry.content in history_set:
                continue
            line = f"[Memory] {entry.content}" if not parts else entry.content
            tokens = _estimate_tokens(line)
            if used + tokens > budget:
                break
            parts.append(f"[Memory] {entry.content}" if not parts else entry.content)
            used += tokens

        return "\n".join(parts), used


def _format_entity(entity: dict) -> str:
    """Format a knowledge graph entity as a compact string."""
    name = entity.get("name", "unknown")
    props = {k: v for k, v in entity.items() if k not in ("name", "entity_type", "id")}
    if props:
        return f"{name} {props}"
    return name

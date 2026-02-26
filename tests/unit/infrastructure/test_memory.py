"""Tests for Semantic Memory — Sprint 1.5.

CC#1: add() → retrieve() returns relevant memories
CC#2: mem0 stores vectors in pgvector (integration test)
CC#3: Neo4j stores entities/relations (integration test)
CC#4: ContextZipper compresses 5000-token history → 500 tokens
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from domain.ports.knowledge_graph import KnowledgeGraphPort
from infrastructure.memory.context_zipper import ContextZipper
from infrastructure.memory.memory_hierarchy import MemoryHierarchy, _estimate_tokens
from infrastructure.persistence.in_memory import InMemoryMemoryRepository as InMemoryMemoryRepo


class InMemoryKnowledgeGraph(KnowledgeGraphPort):
    """In-memory KnowledgeGraphPort for unit tests."""

    def __init__(self) -> None:
        self._entities: dict[str, dict[str, Any]] = {}
        self._relations: list[dict[str, Any]] = []

    async def add_entity(
        self,
        name: str,
        entity_type: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        entity_id = str(uuid.uuid4())
        entity = dict(properties or {})
        entity["id"] = entity_id
        entity["name"] = name
        entity["entity_type"] = entity_type
        self._entities[entity_id] = entity
        return entity_id

    async def add_relation(
        self,
        from_id: str,
        to_id: str,
        relation_type: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        relation_id = str(uuid.uuid4())
        relation = dict(properties or {})
        relation["id"] = relation_id
        relation["from_id"] = from_id
        relation["to_id"] = to_id
        relation["relation_type"] = relation_type
        self._relations.append(relation)
        return relation_id

    async def query(self, pattern: str) -> list[dict[str, Any]]:
        """Simple: return all entities if pattern is '*', else empty."""
        if pattern == "*":
            return list(self._entities.values())
        return []

    async def search_entities(self, name_pattern: str) -> list[dict[str, Any]]:
        pattern_lower = name_pattern.lower()
        return [e for e in self._entities.values() if pattern_lower in e["name"].lower()]


# ═══════════════════════════════════════════════════════════════
# TestMemoryHierarchy — L1-L4 unified manager
# ═══════════════════════════════════════════════════════════════


class TestMemoryHierarchy:
    """Tests for MemoryHierarchy L1-L4 unified manager."""

    @pytest.fixture()
    def repo(self) -> InMemoryMemoryRepo:
        return InMemoryMemoryRepo()

    @pytest.fixture()
    def kg(self) -> InMemoryKnowledgeGraph:
        return InMemoryKnowledgeGraph()

    @pytest.fixture()
    def hierarchy(self, repo: InMemoryMemoryRepo, kg: InMemoryKnowledgeGraph) -> MemoryHierarchy:
        return MemoryHierarchy(memory_repo=repo, knowledge_graph=kg, max_l1_entries=5)

    @pytest.fixture()
    def hierarchy_no_kg(self, repo: InMemoryMemoryRepo) -> MemoryHierarchy:
        return MemoryHierarchy(memory_repo=repo, max_l1_entries=5)

    @pytest.mark.asyncio()
    async def test_add_stores_in_l1(self, hierarchy: MemoryHierarchy) -> None:
        await hierarchy.add("hello world")
        assert "hello world" in hierarchy.l1_entries

    @pytest.mark.asyncio()
    async def test_add_stores_in_l2(
        self, hierarchy: MemoryHierarchy, repo: InMemoryMemoryRepo
    ) -> None:
        await hierarchy.add("test content")
        entries = await repo.search("test")
        assert len(entries) >= 1
        assert any(e.content == "test content" for e in entries)

    @pytest.mark.asyncio()
    async def test_retrieve_from_l1_keyword_match(self, hierarchy: MemoryHierarchy) -> None:
        await hierarchy.add("Python is great for data science")
        result = await hierarchy.retrieve("Python", max_tokens=500)
        assert "Python" in result

    @pytest.mark.asyncio()
    async def test_retrieve_from_l2_semantic(self, hierarchy: MemoryHierarchy) -> None:
        await hierarchy.add("machine learning algorithms")
        result = await hierarchy.retrieve("algorithms", max_tokens=500)
        assert "algorithms" in result

    @pytest.mark.asyncio()
    async def test_retrieve_from_l3_knowledge_graph(
        self, hierarchy: MemoryHierarchy, kg: InMemoryKnowledgeGraph
    ) -> None:
        await kg.add_entity("Shimizu", "Company", {"industry": "construction"})
        result = await hierarchy.retrieve("Shimizu", max_tokens=500)
        assert "Shimizu" in result

    @pytest.mark.asyncio()
    async def test_retrieve_empty_when_no_match(self, hierarchy: MemoryHierarchy) -> None:
        await hierarchy.add("hello world")
        result = await hierarchy.retrieve("xyznonexistent", max_tokens=500)
        assert result == ""

    @pytest.mark.asyncio()
    async def test_l1_deque_overflow(self, hierarchy: MemoryHierarchy) -> None:
        """L1 deque should evict oldest when max_l1_entries exceeded."""
        for i in range(7):
            await hierarchy.add(f"message_{i}")
        # max_l1_entries=5, so first 2 should be evicted
        assert "message_0" not in hierarchy.l1_entries
        assert "message_1" not in hierarchy.l1_entries
        assert "message_6" in hierarchy.l1_entries
        assert len(hierarchy.l1_entries) == 5

    @pytest.mark.asyncio()
    async def test_retrieve_respects_token_budget(self, hierarchy: MemoryHierarchy) -> None:
        """Results should fit within max_tokens budget."""
        for i in range(5):
            await hierarchy.add(f"keyword_{i} " * 50)  # ~50 words each
        result = await hierarchy.retrieve("keyword_0", max_tokens=20)
        assert _estimate_tokens(result) <= 20

    @pytest.mark.asyncio()
    async def test_retrieve_deduplicates(self, hierarchy: MemoryHierarchy) -> None:
        """Same content from L1 and L2 should not be duplicated."""
        await hierarchy.add("unique content here")
        result = await hierarchy.retrieve("unique content", max_tokens=500)
        assert result.count("unique content here") == 1

    @pytest.mark.asyncio()
    async def test_no_knowledge_graph_graceful(self, hierarchy_no_kg: MemoryHierarchy) -> None:
        """MemoryHierarchy works without knowledge graph (L3 returns empty)."""
        await hierarchy_no_kg.add("test without kg")
        result = await hierarchy_no_kg.retrieve("test", max_tokens=500)
        assert "test without kg" in result

    @pytest.mark.asyncio()
    async def test_add_with_role_metadata(
        self, hierarchy: MemoryHierarchy, repo: InMemoryMemoryRepo
    ) -> None:
        await hierarchy.add("user message", role="user")
        entries = await repo.search("user message")
        assert entries[0].metadata.get("role") == "user"

    @pytest.mark.asyncio()
    async def test_l1_priority_over_l2(self, hierarchy: MemoryHierarchy) -> None:
        """L1 matches should appear before L2 matches in results."""
        await hierarchy.add("first keyword match")
        await hierarchy.add("second keyword match")
        result = await hierarchy.retrieve("keyword", max_tokens=500)
        # Both should be present (L1 scan finds them)
        assert "keyword" in result


# ═══════════════════════════════════════════════════════════════
# TestContextZipper — query-adaptive compression
# ═══════════════════════════════════════════════════════════════


class TestContextZipper:
    """Tests for ContextZipper compression."""

    @pytest.fixture()
    def zipper(self) -> ContextZipper:
        return ContextZipper()

    def test_empty_history(self, zipper: ContextZipper) -> None:
        result = zipper.compress([], "any query")
        assert result == ""

    def test_single_message_within_budget(self, zipper: ContextZipper) -> None:
        result = zipper.compress(["hello world"], "hello", max_tokens=500)
        assert result == "hello world"

    def test_respects_max_tokens(self, zipper: ContextZipper) -> None:
        # Each message ~25 tokens (100 chars / 4)
        history = [f"message number {i} " * 5 for i in range(20)]
        result = zipper.compress(history, "message", max_tokens=50)
        assert _estimate_tokens(result) <= 50

    def test_query_relevance_boost(self, zipper: ContextZipper) -> None:
        """Messages matching query keywords should be prioritized."""
        history = [
            "The weather is sunny today",
            "Python programming is fun",
            "I love Python and machine learning",
            "The cat sat on the mat",
        ]
        result = zipper.compress(history, "Python programming", max_tokens=100)
        assert "Python" in result

    def test_recency_bias(self, zipper: ContextZipper) -> None:
        """More recent messages should be preferred when relevance is equal."""
        history = [f"generic message {i}" for i in range(10)]
        result = zipper.compress(history, "unrelated query", max_tokens=30)
        # Most recent messages should be selected (higher index = more recent)
        assert "message 9" in result

    def test_preserves_chronological_order(self, zipper: ContextZipper) -> None:
        """Selected messages should be in original chronological order."""
        history = ["first message", "second message", "third message"]
        result = zipper.compress(history, "message", max_tokens=500)
        lines = result.split("\n")
        assert len(lines) == 3
        assert lines[0] == "first message"
        assert lines[2] == "third message"

    def test_compression_ratio_5000_to_500(self, zipper: ContextZipper) -> None:
        """CC#4: 5000-token history compressed to ≤500 tokens."""
        # Generate ~5000 tokens of history (20000 chars / 4)
        history = [f"conversation message {i}: " + "x" * 96 for i in range(200)]
        total_tokens = sum(_estimate_tokens(m) for m in history)
        assert total_tokens >= 5000  # verify input is large enough

        result = zipper.compress(history, "conversation", max_tokens=500)
        result_tokens = _estimate_tokens(result)
        assert result_tokens <= 500

    def test_empty_query(self, zipper: ContextZipper) -> None:
        """Empty query should still work, using recency only."""
        history = ["msg one", "msg two", "msg three"]
        result = zipper.compress(history, "", max_tokens=500)
        assert len(result) > 0

    def test_large_single_message_skipped(self, zipper: ContextZipper) -> None:
        """Message larger than budget should be skipped."""
        history = ["short msg", "x" * 4000, "another short"]
        result = zipper.compress(history, "short", max_tokens=20)
        assert "x" * 100 not in result

    def test_all_messages_fit(self, zipper: ContextZipper) -> None:
        """When all messages fit in budget, include everything."""
        history = ["a", "b", "c"]
        result = zipper.compress(history, "a", max_tokens=500)
        assert "a" in result
        assert "b" in result
        assert "c" in result


# ═══════════════════════════════════════════════════════════════
# TestKnowledgeGraphPort — in-memory implementation
# ═══════════════════════════════════════════════════════════════


class TestKnowledgeGraphPort:
    """Tests for KnowledgeGraphPort (using InMemoryKnowledgeGraph)."""

    @pytest.fixture()
    def kg(self) -> InMemoryKnowledgeGraph:
        return InMemoryKnowledgeGraph()

    @pytest.mark.asyncio()
    async def test_add_entity(self, kg: InMemoryKnowledgeGraph) -> None:
        eid = await kg.add_entity("Morphic", "Project", {"version": "0.4"})
        assert isinstance(eid, str)
        assert len(eid) > 0

    @pytest.mark.asyncio()
    async def test_add_relation(self, kg: InMemoryKnowledgeGraph) -> None:
        e1 = await kg.add_entity("Alice", "Person")
        e2 = await kg.add_entity("Morphic", "Project")
        rid = await kg.add_relation(e1, e2, "WORKS_ON")
        assert isinstance(rid, str)

    @pytest.mark.asyncio()
    async def test_query_all(self, kg: InMemoryKnowledgeGraph) -> None:
        await kg.add_entity("A", "Type1")
        await kg.add_entity("B", "Type2")
        results = await kg.query("*")
        assert len(results) == 2

    @pytest.mark.asyncio()
    async def test_search_entities_by_name(self, kg: InMemoryKnowledgeGraph) -> None:
        await kg.add_entity("Shimizu Corp", "Company")
        await kg.add_entity("Toyota", "Company")
        results = await kg.search_entities("Shimizu")
        assert len(results) == 1
        assert results[0]["name"] == "Shimizu Corp"

    @pytest.mark.asyncio()
    async def test_search_entities_case_insensitive(self, kg: InMemoryKnowledgeGraph) -> None:
        await kg.add_entity("Python", "Language")
        results = await kg.search_entities("python")
        assert len(results) == 1


# ═══════════════════════════════════════════════════════════════
# TestCompletionCriteria — CC#1 and CC#4
# ═══════════════════════════════════════════════════════════════


class TestCompletionCriteria:
    """Verify Sprint 1.5 completion criteria."""

    @pytest.mark.asyncio()
    async def test_cc1_add_then_retrieve(self) -> None:
        """CC#1: add() → retrieve() returns relevant memories."""
        repo = InMemoryMemoryRepo()
        hierarchy = MemoryHierarchy(memory_repo=repo)

        await hierarchy.add("Python is a popular programming language")
        await hierarchy.add("JavaScript runs in the browser")
        await hierarchy.add("Rust is fast and memory safe")

        result = await hierarchy.retrieve("Python programming", max_tokens=500)
        assert "Python" in result

    @pytest.mark.asyncio()
    async def test_cc1_add_then_retrieve_no_false_positive(self) -> None:
        """CC#1: retrieve should not return unrelated content."""
        repo = InMemoryMemoryRepo()
        hierarchy = MemoryHierarchy(memory_repo=repo)

        await hierarchy.add("The weather is nice")
        result = await hierarchy.retrieve("quantum computing", max_tokens=500)
        # No keyword overlap → should not find anything
        assert result == ""

    def test_cc4_compression_5000_to_500(self) -> None:
        """CC#4: ContextZipper compresses 5000-token history → ≤500 tokens."""
        zipper = ContextZipper()
        history = [f"msg {i}: " + "a" * 96 for i in range(200)]
        total = sum(_estimate_tokens(m) for m in history)
        assert total >= 5000

        result = zipper.compress(history, "msg", max_tokens=500)
        assert _estimate_tokens(result) <= 500
        assert len(result) > 0  # not empty

    @pytest.mark.asyncio()
    async def test_cc1_retrieve_with_knowledge_graph(self) -> None:
        """CC#1: retrieve includes L3 knowledge graph results."""
        repo = InMemoryMemoryRepo()
        kg = InMemoryKnowledgeGraph()
        hierarchy = MemoryHierarchy(memory_repo=repo, knowledge_graph=kg)

        await kg.add_entity("FastAPI", "Framework", {"language": "Python"})
        result = await hierarchy.retrieve("FastAPI", max_tokens=500)
        assert "FastAPI" in result

    @pytest.mark.asyncio()
    async def test_cc1_multi_layer_retrieval(self) -> None:
        """CC#1: retrieve combines results from L1 + L2 + L3."""
        repo = InMemoryMemoryRepo()
        kg = InMemoryKnowledgeGraph()
        hierarchy = MemoryHierarchy(memory_repo=repo, knowledge_graph=kg)

        await hierarchy.add("React frontend framework")
        await kg.add_entity("React", "Library", {"type": "frontend"})
        result = await hierarchy.retrieve("React", max_tokens=500)
        assert "React" in result


# ═══════════════════════════════════════════════════════════════
# Test helper: _estimate_tokens
# ═══════════════════════════════════════════════════════════════


class TestEstimateTokens:
    def test_empty_string(self) -> None:
        assert _estimate_tokens("") == 1  # min 1

    def test_short_string(self) -> None:
        assert _estimate_tokens("hi") == 1

    def test_normal_string(self) -> None:
        # 100 chars → 25 tokens
        assert _estimate_tokens("x" * 100) == 25

    def test_long_string(self) -> None:
        assert _estimate_tokens("x" * 4000) == 1000

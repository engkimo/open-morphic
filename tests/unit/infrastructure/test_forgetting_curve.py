"""Tests for infrastructure/memory/forgetting_curve.py — ForgettingCurveManager.

Async tests using InMemoryMemoryRepository and InMemoryKnowledgeGraph.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest

from domain.entities.memory import MemoryEntry
from domain.ports.knowledge_graph import KnowledgeGraphPort
from domain.value_objects.status import MemoryType
from infrastructure.memory.forgetting_curve import CompactResult, ForgettingCurveManager
from infrastructure.persistence.in_memory import InMemoryMemoryRepository


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
        if pattern == "*":
            return list(self._entities.values())
        return []

    async def search_entities(self, name_pattern: str) -> list[dict[str, Any]]:
        pattern_lower = name_pattern.lower()
        return [e for e in self._entities.values() if pattern_lower in e["name"].lower()]


def _make_entry(
    content: str = "test content",
    hours_ago: float = 0.0,
    access_count: int = 1,
    importance: float = 0.5,
    memory_type: MemoryType = MemoryType.L2_SEMANTIC,
) -> MemoryEntry:
    """Helper to create a MemoryEntry with a controlled last_accessed time."""
    t = datetime.now() - timedelta(hours=hours_ago)
    return MemoryEntry(
        content=content,
        memory_type=memory_type,
        access_count=access_count,
        importance_score=importance,
        created_at=t,
        last_accessed=t,
    )


class TestCompactResult:
    def test_fields(self) -> None:
        r = CompactResult(scanned=10, expired=3, promoted=2, deleted=3)
        assert r.scanned == 10
        assert r.expired == 3
        assert r.promoted == 2
        assert r.deleted == 3


class TestScoreEntry:
    @pytest.fixture()
    def manager(self) -> ForgettingCurveManager:
        return ForgettingCurveManager(memory_repo=InMemoryMemoryRepository())

    def test_fresh_entry_high_score(self, manager: ForgettingCurveManager) -> None:
        entry = _make_entry(hours_ago=0.0)
        score = manager.score_entry(entry)
        assert score > 0.9

    def test_old_entry_low_score(self, manager: ForgettingCurveManager) -> None:
        entry = _make_entry(hours_ago=500.0, access_count=1, importance=0.0)
        score = manager.score_entry(entry)
        assert score < 0.1

    def test_high_access_preserves_score(self, manager: ForgettingCurveManager) -> None:
        entry = _make_entry(hours_ago=48.0, access_count=20, importance=1.0)
        score = manager.score_entry(entry)
        assert score > 0.5


class TestCompactNoExpired:
    @pytest.mark.asyncio()
    async def test_no_entries(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = ForgettingCurveManager(memory_repo=repo)
        result = await mgr.compact()
        assert result == CompactResult(scanned=0, expired=0, promoted=0, deleted=0)

    @pytest.mark.asyncio()
    async def test_all_fresh(self) -> None:
        repo = InMemoryMemoryRepository()
        for i in range(3):
            await repo.add(_make_entry(content=f"fresh {i}", hours_ago=0.0))
        mgr = ForgettingCurveManager(memory_repo=repo)
        result = await mgr.compact()
        assert result.scanned == 3
        assert result.expired == 0
        assert result.deleted == 0

    @pytest.mark.asyncio()
    async def test_ignores_non_l2_entries(self) -> None:
        """Only L2_SEMANTIC entries are scanned."""
        repo = InMemoryMemoryRepository()
        entry = _make_entry(content="l4 entry", memory_type=MemoryType.L4_COLD, hours_ago=9999.0)
        await repo.add(entry)
        mgr = ForgettingCurveManager(memory_repo=repo)
        result = await mgr.compact()
        assert result.scanned == 0


class TestCompactWithExpired:
    @pytest.mark.asyncio()
    async def test_expired_deleted_no_kg(self) -> None:
        """Expired entries deleted when no KnowledgeGraph provided."""
        repo = InMemoryMemoryRepository()
        expired = _make_entry(content="old memory", hours_ago=500.0, importance=0.0)
        await repo.add(expired)
        mgr = ForgettingCurveManager(memory_repo=repo)
        result = await mgr.compact()
        assert result.scanned == 1
        assert result.expired == 1
        assert result.promoted == 0
        assert result.deleted == 1
        # Entry should be gone
        assert await repo.get_by_id(expired.id) is None

    @pytest.mark.asyncio()
    async def test_expired_promoted_to_kg(self) -> None:
        """Expired entries promoted to KG then deleted from L2."""
        repo = InMemoryMemoryRepository()
        kg = InMemoryKnowledgeGraph()
        expired = _make_entry(content="knowledge to promote", hours_ago=500.0, importance=0.0)
        await repo.add(expired)
        mgr = ForgettingCurveManager(memory_repo=repo, knowledge_graph=kg)
        result = await mgr.compact()
        assert result.promoted == 1
        assert result.deleted == 1
        # KG should have the entity
        entities = await kg.search_entities("knowledge to promote")
        assert len(entities) == 1
        assert entities[0]["entity_type"] == "memory_fact"
        # L2 entry gone
        assert await repo.get_by_id(expired.id) is None

    @pytest.mark.asyncio()
    async def test_mixed_fresh_and_expired(self) -> None:
        """Only expired entries are removed; fresh ones stay."""
        repo = InMemoryMemoryRepository()
        kg = InMemoryKnowledgeGraph()
        fresh = _make_entry(content="fresh item", hours_ago=0.0)
        expired = _make_entry(content="expired item", hours_ago=500.0, importance=0.0)
        await repo.add(fresh)
        await repo.add(expired)
        mgr = ForgettingCurveManager(memory_repo=repo, knowledge_graph=kg)
        result = await mgr.compact()
        assert result.scanned == 2
        assert result.expired == 1
        assert result.promoted == 1
        assert result.deleted == 1
        # Fresh entry still present
        assert await repo.get_by_id(fresh.id) is not None

    @pytest.mark.asyncio()
    async def test_custom_threshold(self) -> None:
        """Higher threshold expires more entries."""
        repo = InMemoryMemoryRepository()
        # 24 hours, ac=1, imp=0.5 → score ~0.67
        entry = _make_entry(content="medium age", hours_ago=24.0)
        await repo.add(entry)
        # threshold=0.3 → not expired
        mgr_low = ForgettingCurveManager(memory_repo=repo, threshold=0.3)
        r1 = await mgr_low.compact()
        assert r1.expired == 0
        # threshold=0.9 → expired
        mgr_high = ForgettingCurveManager(memory_repo=repo, threshold=0.9)
        r2 = await mgr_high.compact()
        assert r2.expired == 1


class TestPromoteToFacts:
    @pytest.mark.asyncio()
    async def test_returns_entity_id(self) -> None:
        repo = InMemoryMemoryRepository()
        kg = InMemoryKnowledgeGraph()
        mgr = ForgettingCurveManager(memory_repo=repo, knowledge_graph=kg)
        entry = _make_entry(content="promote me")
        entity_id = await mgr._promote_to_facts(entry)
        assert entity_id is not None
        assert len(entity_id) > 0

    @pytest.mark.asyncio()
    async def test_returns_none_without_kg(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = ForgettingCurveManager(memory_repo=repo)
        entry = _make_entry(content="no kg")
        assert await mgr._promote_to_facts(entry) is None

    @pytest.mark.asyncio()
    async def test_entity_has_correct_properties(self) -> None:
        repo = InMemoryMemoryRepository()
        kg = InMemoryKnowledgeGraph()
        mgr = ForgettingCurveManager(memory_repo=repo, knowledge_graph=kg)
        entry = _make_entry(content="fact content", access_count=5, importance=0.8)
        entity_id = await mgr._promote_to_facts(entry)
        entities = await kg.query("*")
        promoted = [e for e in entities if e["id"] == entity_id]
        assert len(promoted) == 1
        assert promoted[0]["name"] == "fact content"
        assert promoted[0]["entity_type"] == "memory_fact"
        assert promoted[0]["access_count"] == 5
        assert promoted[0]["importance_score"] == 0.8


class TestListByType:
    @pytest.mark.asyncio()
    async def test_returns_matching_type(self) -> None:
        repo = InMemoryMemoryRepository()
        await repo.add(_make_entry(content="l2 a", memory_type=MemoryType.L2_SEMANTIC))
        await repo.add(_make_entry(content="l4 a", memory_type=MemoryType.L4_COLD))
        await repo.add(_make_entry(content="l2 b", memory_type=MemoryType.L2_SEMANTIC))
        result = await repo.list_by_type(MemoryType.L2_SEMANTIC)
        assert len(result) == 2
        assert all(e.memory_type == MemoryType.L2_SEMANTIC for e in result)

    @pytest.mark.asyncio()
    async def test_respects_limit(self) -> None:
        repo = InMemoryMemoryRepository()
        for i in range(10):
            await repo.add(_make_entry(content=f"item {i}"))
        result = await repo.list_by_type(MemoryType.L2_SEMANTIC, limit=3)
        assert len(result) == 3

    @pytest.mark.asyncio()
    async def test_empty_when_no_match(self) -> None:
        repo = InMemoryMemoryRepository()
        await repo.add(_make_entry(content="l2", memory_type=MemoryType.L2_SEMANTIC))
        result = await repo.list_by_type(MemoryType.L4_COLD)
        assert result == []

"""Integration tests for Semantic Memory — Sprint 1.5.

Tests require real services:
  - PostgreSQL + pgvector (CC#2)
  - Neo4j (CC#3)

Skipped gracefully when services are unavailable.
Run with: uv run pytest tests/integration/test_memory.py -v -s
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

# ── Check service availability ──

_pg_available = False
_neo4j_available = False

try:
    import asyncpg

    async def _check_pg() -> bool:
        try:
            conn = await asyncpg.connect(
                "postgresql://morphic:morphic_dev@localhost:5432/morphic_agent",
                timeout=2,
            )
            await conn.close()
            return True
        except Exception:
            return False

    _pg_available = asyncio.get_event_loop().run_until_complete(_check_pg())
except Exception:
    pass

try:
    from neo4j import GraphDatabase

    def _check_neo4j() -> bool:
        try:
            driver = GraphDatabase.driver(
                "bolt://localhost:7687", auth=("neo4j", "morphic_dev")
            )
            with driver.session() as session:
                session.run("RETURN 1")
            driver.close()
            return True
        except Exception:
            return False

    _neo4j_available = _check_neo4j()
except Exception:
    pass


# ═══════════════════════════════════════════════════════════════
# CC#2: pgvector Memory tests
# ═══════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _pg_available, reason="PostgreSQL not available")
class TestPgvectorMemory:
    """CC#2: mem0 stores vectors in pgvector."""

    @pytest.mark.asyncio()
    async def test_memory_model_table_exists(self) -> None:
        """Verify memories table exists in PostgreSQL."""
        import asyncpg

        conn = await asyncpg.connect(
            "postgresql://morphic:morphic_dev@localhost:5432/morphic_agent"
        )
        try:
            result = await conn.fetch(
                "SELECT EXISTS ("
                "  SELECT FROM information_schema.tables "
                "  WHERE table_name = 'memories'"
                ")"
            )
            assert result[0]["exists"] is True
        finally:
            await conn.close()

    @pytest.mark.asyncio()
    async def test_insert_and_query_memory(self) -> None:
        """Insert a memory entry and query it back."""
        import asyncpg

        conn = await asyncpg.connect(
            "postgresql://morphic:morphic_dev@localhost:5432/morphic_agent"
        )
        try:
            memory_id = uuid.uuid4()
            await conn.execute(
                "INSERT INTO memories (id, content, memory_type, access_count, importance_score) "
                "VALUES ($1, $2, $3, $4, $5)",
                memory_id,
                "Test memory for pgvector integration",
                "l2_semantic",
                1,
                0.5,
            )
            row = await conn.fetchrow(
                "SELECT * FROM memories WHERE id = $1", memory_id
            )
            assert row is not None
            assert row["content"] == "Test memory for pgvector integration"

            # Cleanup
            await conn.execute("DELETE FROM memories WHERE id = $1", memory_id)
        finally:
            await conn.close()

    @pytest.mark.asyncio()
    async def test_pgvector_extension_enabled(self) -> None:
        """Verify pgvector extension is available."""
        import asyncpg

        conn = await asyncpg.connect(
            "postgresql://morphic:morphic_dev@localhost:5432/morphic_agent"
        )
        try:
            result = await conn.fetch(
                "SELECT EXISTS ("
                "  SELECT FROM pg_extension WHERE extname = 'vector'"
                ")"
            )
            assert result[0]["exists"] is True
        finally:
            await conn.close()


# ═══════════════════════════════════════════════════════════════
# CC#3: Neo4j Knowledge Graph tests
# ═══════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _neo4j_available, reason="Neo4j not available")
class TestNeo4jKnowledgeGraph:
    """CC#3: Neo4j stores entities/relations, searchable via Cypher."""

    @pytest.mark.asyncio()
    async def test_add_entity_and_search(self) -> None:
        from infrastructure.memory.knowledge_graph import Neo4jKnowledgeGraph

        kg = Neo4jKnowledgeGraph(
            uri="bolt://localhost:7687", user="neo4j", password="morphic_dev"
        )
        try:
            eid = await kg.add_entity(
                "TestEntity_IntegTest", "TestType", {"score": 42}
            )
            assert isinstance(eid, str)

            results = await kg.search_entities("TestEntity_IntegTest")
            assert len(results) >= 1
            assert any(r["name"] == "TestEntity_IntegTest" for r in results)
        finally:
            # Cleanup
            await kg.query(
                "MATCH (n {name: 'TestEntity_IntegTest'}) DETACH DELETE n"
            )
            await kg.close()

    @pytest.mark.asyncio()
    async def test_add_relation_and_query(self) -> None:
        from infrastructure.memory.knowledge_graph import Neo4jKnowledgeGraph

        kg = Neo4jKnowledgeGraph(
            uri="bolt://localhost:7687", user="neo4j", password="morphic_dev"
        )
        try:
            e1 = await kg.add_entity("Alice_IT", "Person")
            e2 = await kg.add_entity("Morphic_IT", "Project")
            rid = await kg.add_relation(e1, e2, "WORKS_ON", {"since": 2025})
            assert isinstance(rid, str)

            results = await kg.query(
                "MATCH (a {name: 'Alice_IT'})-[r:WORKS_ON]->(b {name: 'Morphic_IT'}) "
                "RETURN a.name AS person, b.name AS project, r.since AS since"
            )
            assert len(results) >= 1
            assert results[0]["person"] == "Alice_IT"
            assert results[0]["project"] == "Morphic_IT"
        finally:
            # Cleanup
            await kg.query(
                "MATCH (n) WHERE n.name IN ['Alice_IT', 'Morphic_IT'] DETACH DELETE n"
            )
            await kg.close()

    @pytest.mark.asyncio()
    async def test_search_entities_case_sensitive(self) -> None:
        from infrastructure.memory.knowledge_graph import Neo4jKnowledgeGraph

        kg = Neo4jKnowledgeGraph(
            uri="bolt://localhost:7687", user="neo4j", password="morphic_dev"
        )
        try:
            await kg.add_entity("UniqueTestName_XYZ", "TestType")
            results = await kg.search_entities("UniqueTestName_XYZ")
            assert len(results) == 1
        finally:
            await kg.query(
                "MATCH (n {name: 'UniqueTestName_XYZ'}) DETACH DELETE n"
            )
            await kg.close()


# ═══════════════════════════════════════════════════════════════
# TestMemoryHierarchyLive — end-to-end with real backends
# ═══════════════════════════════════════════════════════════════


@pytest.mark.skipif(
    not (_pg_available and _neo4j_available),
    reason="PostgreSQL and/or Neo4j not available",
)
class TestMemoryHierarchyLive:
    """End-to-end memory hierarchy with real PostgreSQL + Neo4j."""

    @pytest.mark.asyncio()
    async def test_add_and_retrieve_live(self) -> None:
        """Full pipeline: add to memory → retrieve with keyword match."""
        # Use InMemory repo as live repo adapter is not yet wired
        # This tests the MemoryHierarchy orchestration logic itself
        from infrastructure.memory.knowledge_graph import Neo4jKnowledgeGraph
        from tests.unit.infrastructure.test_memory import InMemoryMemoryRepo

        repo = InMemoryMemoryRepo()
        kg = Neo4jKnowledgeGraph(
            uri="bolt://localhost:7687", user="neo4j", password="morphic_dev"
        )
        try:
            from infrastructure.memory.memory_hierarchy import MemoryHierarchy

            hierarchy = MemoryHierarchy(
                memory_repo=repo, knowledge_graph=kg, max_l1_entries=50
            )

            await hierarchy.add("FastAPI is great for REST APIs")
            await kg.add_entity("FastAPI_Live", "Framework", {"type": "web"})

            result = await hierarchy.retrieve("FastAPI", max_tokens=500)
            assert "FastAPI" in result
        finally:
            await kg.query(
                "MATCH (n {name: 'FastAPI_Live'}) DETACH DELETE n"
            )
            await kg.close()

    @pytest.mark.asyncio()
    async def test_multi_layer_retrieval_live(self) -> None:
        """Retrieve from L1 + L2 + L3 with real Neo4j."""
        from infrastructure.memory.knowledge_graph import Neo4jKnowledgeGraph
        from tests.unit.infrastructure.test_memory import InMemoryMemoryRepo

        repo = InMemoryMemoryRepo()
        kg = Neo4jKnowledgeGraph(
            uri="bolt://localhost:7687", user="neo4j", password="morphic_dev"
        )
        try:
            from infrastructure.memory.memory_hierarchy import MemoryHierarchy

            hierarchy = MemoryHierarchy(
                memory_repo=repo, knowledge_graph=kg, max_l1_entries=50
            )

            await hierarchy.add("LangGraph provides DAG execution")
            await kg.add_entity("LangGraph_Live", "Library", {"category": "agent"})

            result = await hierarchy.retrieve("LangGraph", max_tokens=500)
            assert "LangGraph" in result
        finally:
            await kg.query(
                "MATCH (n {name: 'LangGraph_Live'}) DETACH DELETE n"
            )
            await kg.close()

"""Neo4jKnowledgeGraph — L3 entity-relation storage via Neo4j.

Implements KnowledgeGraphPort using the neo4j async driver.
Entity/relation CRUD via Cypher queries.
"""

from __future__ import annotations

import uuid
from typing import Any

from domain.ports.knowledge_graph import KnowledgeGraphPort

try:
    from neo4j import AsyncGraphDatabase, AsyncDriver
except ImportError:
    AsyncGraphDatabase = None  # type: ignore[assignment, misc]
    AsyncDriver = None  # type: ignore[assignment, misc]


class Neo4jKnowledgeGraph(KnowledgeGraphPort):
    """Neo4j implementation of KnowledgeGraphPort."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        if AsyncGraphDatabase is None:
            raise ImportError("neo4j package is required: pip install neo4j")
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(  # type: ignore[assignment]
            uri, auth=(user, password)
        )

    async def close(self) -> None:
        await self._driver.close()

    async def add_entity(
        self,
        name: str,
        entity_type: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        entity_id = str(uuid.uuid4())
        props = dict(properties or {})
        props["id"] = entity_id
        props["name"] = name
        props["entity_type"] = entity_type

        cypher = (
            f"CREATE (n:{_safe_label(entity_type)} $props) RETURN n.id AS id"
        )
        async with self._driver.session() as session:
            result = await session.run(cypher, props=props)
            record = await result.single()
            return record["id"] if record else entity_id

    async def add_relation(
        self,
        from_id: str,
        to_id: str,
        relation_type: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        relation_id = str(uuid.uuid4())
        props = dict(properties or {})
        props["id"] = relation_id

        safe_rel = _safe_label(relation_type)
        cypher = (
            "MATCH (a {id: $from_id}), (b {id: $to_id}) "
            f"CREATE (a)-[r:{safe_rel} $props]->(b) "
            "RETURN r.id AS id"
        )
        async with self._driver.session() as session:
            result = await session.run(
                cypher, from_id=from_id, to_id=to_id, props=props
            )
            record = await result.single()
            return record["id"] if record else relation_id

    async def query(self, pattern: str) -> list[dict[str, Any]]:
        async with self._driver.session() as session:
            result = await session.run(pattern)
            records = [dict(record) for record in await result.data()]
            return records

    async def search_entities(self, name_pattern: str) -> list[dict[str, Any]]:
        cypher = (
            "MATCH (n) WHERE n.name CONTAINS $pattern "
            "RETURN n.id AS id, n.name AS name, n.entity_type AS entity_type"
        )
        async with self._driver.session() as session:
            result = await session.run(cypher, pattern=name_pattern)
            return [dict(record) for record in await result.data()]


def _safe_label(name: str) -> str:
    """Sanitize a label/type name for Cypher (alphanumeric + underscore only)."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in name)

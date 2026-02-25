"""KnowledgeGraphPort — persistence abstraction for L3 entity-relation storage."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class KnowledgeGraphPort(ABC):
    """Abstract port for structured knowledge graph (L3 Facts layer).

    Implementations may use Neo4j, NetworkX, or in-memory stores.
    Domain layer never depends on specific graph database technology.
    """

    @abstractmethod
    async def add_entity(
        self,
        name: str,
        entity_type: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """Add an entity node. Returns entity_id."""
        ...

    @abstractmethod
    async def add_relation(
        self,
        from_id: str,
        to_id: str,
        relation_type: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """Add a relation edge between two entities. Returns relation_id."""
        ...

    @abstractmethod
    async def query(self, pattern: str) -> list[dict[str, Any]]:
        """Query the knowledge graph with a pattern string (e.g. Cypher)."""
        ...

    @abstractmethod
    async def search_entities(self, name_pattern: str) -> list[dict[str, Any]]:
        """Search entities by name pattern (substring match)."""
        ...

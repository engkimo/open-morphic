"""ToolRegistryPort — abstract interface for searching tool registries.

Domain defines WHAT it needs. Infrastructure provides HOW.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from domain.entities.tool_candidate import ToolCandidate


@dataclass
class ToolSearchResult:
    """Result from a registry search."""

    query: str
    candidates: list[ToolCandidate] = field(default_factory=list)
    total_count: int = 0
    error: str | None = None


class ToolRegistryPort(ABC):
    """Port for searching tool registries (MCP Registry, etc.)."""

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> ToolSearchResult:
        """Search for tools matching query.

        Args:
            query: Search term (tool name, capability, etc.).
            limit: Maximum results to return.

        Returns:
            ToolSearchResult with scored candidates.
        """
        ...

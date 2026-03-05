"""DiscoverToolsUseCase — analyze failure, search registry, return suggestions."""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.entities.tool_candidate import ToolCandidate
from domain.ports.tool_registry import ToolRegistryPort
from domain.services.failure_analyzer import FailureAnalyzer


@dataclass
class ToolSuggestions:
    """Result from auto tool discovery."""

    suggestions: list[ToolCandidate] = field(default_factory=list)
    queries_used: list[str] = field(default_factory=list)


class DiscoverToolsUseCase:
    """Analyze a task failure and suggest relevant tools."""

    def __init__(
        self,
        registry: ToolRegistryPort,
        analyzer: FailureAnalyzer | None = None,
    ) -> None:
        self._registry = registry
        self._analyzer = analyzer or FailureAnalyzer()

    async def suggest_for_failure(
        self,
        error_message: str,
        task_description: str = "",
        max_results: int = 5,
    ) -> ToolSuggestions:
        """Extract queries from error, search registry, return top suggestions."""
        queries = self._analyzer.extract_queries_with_context(error_message, task_description)

        if not queries:
            return ToolSuggestions()

        # Search top-3 queries
        all_candidates: list[ToolCandidate] = []
        seen_names: set[str] = set()

        for query in queries[:3]:
            result = await self._registry.search(query, limit=3)
            for candidate in result.candidates:
                if candidate.name not in seen_names:
                    all_candidates.append(candidate)
                    seen_names.add(candidate.name)

        # Sort by safety score descending
        all_candidates.sort(key=lambda c: c.safety_score, reverse=True)

        return ToolSuggestions(
            suggestions=all_candidates[:max_results],
            queries_used=queries[:3],
        )

"""In-memory implementation of FractalLearningRepository.

Sprint 15.7 (TD-105): Simple dict-based storage for MVP learning.
Production path: migrate to PostgreSQL or knowledge graph later.
"""

from __future__ import annotations

from domain.entities.fractal_learning import ErrorPattern, SuccessfulPath
from domain.ports.fractal_learning_repository import FractalLearningRepository
from domain.services.fractal_learner import FractalLearner


class InMemoryFractalLearningRepository(FractalLearningRepository):
    """In-memory storage for error patterns and successful paths."""

    def __init__(self) -> None:
        self._error_patterns: dict[str, ErrorPattern] = {}
        self._successful_paths: dict[str, SuccessfulPath] = {}

    # -- Error patterns --

    async def save_error_pattern(self, pattern: ErrorPattern) -> None:
        """Save or merge an error pattern."""
        # Check for existing match
        for existing in self._error_patterns.values():
            if (
                existing.goal_fragment == pattern.goal_fragment
                and existing.node_description == pattern.node_description
                and existing.error_message == pattern.error_message
            ):
                FractalLearner.merge_error_pattern(existing, pattern)
                return
        self._error_patterns[pattern.id] = pattern

    async def find_error_patterns(self, goal: str, node_desc: str) -> list[ErrorPattern]:
        """Find matching error patterns."""
        return [p for p in self._error_patterns.values() if p.matches(goal, node_desc)]

    async def find_error_patterns_by_goal(self, goal: str) -> list[ErrorPattern]:
        """Find error patterns matching a goal (ignoring node description)."""
        return [p for p in self._error_patterns.values() if p.matches_goal(goal)]

    async def list_error_patterns(self, limit: int = 50) -> list[ErrorPattern]:
        """List patterns by occurrence count descending."""
        patterns = sorted(
            self._error_patterns.values(),
            key=lambda p: p.occurrence_count,
            reverse=True,
        )
        return patterns[:limit]

    # -- Successful paths --

    async def save_successful_path(self, path: SuccessfulPath) -> None:
        """Save or merge a successful path."""
        for existing in self._successful_paths.values():
            if (
                existing.goal_fragment == path.goal_fragment
                and existing.node_descriptions == path.node_descriptions
            ):
                FractalLearner.merge_successful_path(existing, path)
                return
        self._successful_paths[path.id] = path

    async def find_successful_paths(self, goal: str) -> list[SuccessfulPath]:
        """Find matching successful paths."""
        return [p for p in self._successful_paths.values() if p.matches_goal(goal)]

    async def list_successful_paths(self, limit: int = 50) -> list[SuccessfulPath]:
        """List paths by usage count descending."""
        paths = sorted(
            self._successful_paths.values(),
            key=lambda p: p.usage_count,
            reverse=True,
        )
        return paths[:limit]

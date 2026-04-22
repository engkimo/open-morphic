"""Port for fractal learning data persistence.

Sprint 15.7 (TD-105): ABC for storing and retrieving error patterns
and successful execution paths.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.fractal_learning import ErrorPattern, SuccessfulPath


class FractalLearningRepository(ABC):
    """Persistence port for fractal engine learning data."""

    # -- Error patterns --

    @abstractmethod
    async def save_error_pattern(self, pattern: ErrorPattern) -> None:
        """Save or update an error pattern."""

    @abstractmethod
    async def find_error_patterns(self, goal: str, node_desc: str) -> list[ErrorPattern]:
        """Find error patterns matching a goal and node description."""

    @abstractmethod
    async def find_error_patterns_by_goal(self, goal: str) -> list[ErrorPattern]:
        """Find error patterns matching a goal (ignoring node description)."""

    @abstractmethod
    async def list_error_patterns(self, limit: int = 50) -> list[ErrorPattern]:
        """List error patterns ordered by occurrence count descending."""

    # -- Successful paths --

    @abstractmethod
    async def save_successful_path(self, path: SuccessfulPath) -> None:
        """Save or update a successful path."""

    @abstractmethod
    async def find_successful_paths(self, goal: str) -> list[SuccessfulPath]:
        """Find successful paths relevant to a goal."""

    @abstractmethod
    async def list_successful_paths(self, limit: int = 50) -> list[SuccessfulPath]:
        """List successful paths ordered by usage count descending."""

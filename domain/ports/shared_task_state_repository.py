"""SharedTaskStateRepository port — storage for cross-agent task state.

Domain defines WHAT it needs. Infrastructure provides HOW.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.cognitive import AgentAction, SharedTaskState


class SharedTaskStateRepository(ABC):
    """Port for persisting and querying shared task state."""

    @abstractmethod
    async def save(self, state: SharedTaskState) -> None:
        """Persist a shared task state (create or full overwrite)."""
        ...

    @abstractmethod
    async def get(self, task_id: str) -> SharedTaskState | None:
        """Retrieve shared state by task_id, or None if not found."""
        ...

    @abstractmethod
    async def list_active(self) -> list[SharedTaskState]:
        """List all shared task states that have non-empty blockers or recent activity."""
        ...

    @abstractmethod
    async def update_decisions(self, state: SharedTaskState) -> None:
        """Persist only the decisions list for the given state."""
        ...

    @abstractmethod
    async def update_artifacts(self, state: SharedTaskState) -> None:
        """Persist only the artifacts dict for the given state."""
        ...

    @abstractmethod
    async def append_action(self, task_id: str, action: AgentAction) -> None:
        """Append a single agent action to the history of the given task."""
        ...

    @abstractmethod
    async def delete(self, task_id: str) -> None:
        """Remove a shared task state by task_id."""
        ...

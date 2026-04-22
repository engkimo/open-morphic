"""InMemorySharedTaskStateRepository — in-memory impl of SharedTaskStateRepository.

Dev/testing without database. PG migration planned for later phases.
"""

from __future__ import annotations

from datetime import UTC, datetime

from domain.entities.cognitive import AgentAction, SharedTaskState
from domain.ports.shared_task_state_repository import SharedTaskStateRepository

# Activity within the last 24 hours counts as "recent" for list_active
_RECENT_HOURS = 24


class InMemorySharedTaskStateRepository(SharedTaskStateRepository):
    """In-memory implementation of SharedTaskStateRepository."""

    def __init__(self) -> None:
        self._store: dict[str, SharedTaskState] = {}

    async def save(self, state: SharedTaskState) -> None:
        self._store[state.task_id] = state

    async def get(self, task_id: str) -> SharedTaskState | None:
        return self._store.get(task_id)

    async def list_active(self) -> list[SharedTaskState]:
        now = datetime.now(tz=UTC)
        results: list[SharedTaskState] = []
        for state in self._store.values():
            has_blockers = len(state.blockers) > 0
            updated = state.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            recent = (now - updated).total_seconds() < _RECENT_HOURS * 3600
            if has_blockers or recent:
                results.append(state)
        return sorted(results, key=lambda s: s.updated_at, reverse=True)

    async def update_decisions(self, state: SharedTaskState) -> None:
        existing = self._store.get(state.task_id)
        if existing is None:
            return
        existing.decisions = state.decisions
        existing.updated_at = datetime.now()

    async def update_artifacts(self, state: SharedTaskState) -> None:
        existing = self._store.get(state.task_id)
        if existing is None:
            return
        existing.artifacts = state.artifacts
        existing.updated_at = datetime.now()

    async def append_action(self, task_id: str, action: AgentAction) -> None:
        existing = self._store.get(task_id)
        if existing is None:
            return
        existing.add_action(action)

    async def delete(self, task_id: str) -> None:
        self._store.pop(task_id, None)

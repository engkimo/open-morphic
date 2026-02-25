"""MemoryRepository port — persistence abstraction for semantic memory."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.memory import MemoryEntry


class MemoryRepository(ABC):
    @abstractmethod
    async def add(self, entry: MemoryEntry) -> None: ...

    @abstractmethod
    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]: ...

    @abstractmethod
    async def get_by_id(self, memory_id: str) -> MemoryEntry | None: ...

    @abstractmethod
    async def delete(self, memory_id: str) -> None: ...

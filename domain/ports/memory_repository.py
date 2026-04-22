"""MemoryRepository port — persistence abstraction for semantic memory."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.memory import MemoryEntry
from domain.value_objects.status import MemoryType


class MemoryRepository(ABC):
    @abstractmethod
    async def add(self, entry: MemoryEntry) -> None: ...

    @abstractmethod
    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]: ...

    @abstractmethod
    async def get_by_id(self, memory_id: str) -> MemoryEntry | None: ...

    @abstractmethod
    async def delete(self, memory_id: str) -> None: ...

    @abstractmethod
    async def list_by_type(
        self, memory_type: MemoryType, limit: int = 100
    ) -> list[MemoryEntry]: ...

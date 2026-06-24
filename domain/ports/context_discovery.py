"""Port for read-only workspace context discovery."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.workspace_context import ContextIndex


class ContextDiscoveryPort(ABC):
    """Discover instruction and memory sources without mutating them."""

    @abstractmethod
    async def discover(self, workspace_root: str) -> ContextIndex: ...

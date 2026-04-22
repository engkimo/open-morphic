"""AgentRegistryPort — port for agent discovery and registration.

Agents register themselves (with capabilities), and the A2A router
uses the registry to find suitable receivers for a given action.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.a2a import AgentDescriptor
from domain.value_objects.agent_engine import AgentEngineType


class AgentRegistryPort(ABC):
    """Abstract registry for agent discovery."""

    @abstractmethod
    async def register(self, descriptor: AgentDescriptor) -> None:
        """Register or update an agent descriptor."""
        ...

    @abstractmethod
    async def deregister(self, agent_id: str) -> None:
        """Remove an agent from the registry."""
        ...

    @abstractmethod
    async def lookup(self, agent_id: str) -> AgentDescriptor | None:
        """Look up a single agent by id."""
        ...

    @abstractmethod
    async def lookup_by_engine(self, engine: AgentEngineType) -> AgentDescriptor | None:
        """Look up an agent by engine type."""
        ...

    @abstractmethod
    async def list_available(self) -> list[AgentDescriptor]:
        """Return all agents with status ``'available'``."""
        ...

    @abstractmethod
    async def list_by_capability(self, capability: str) -> list[AgentDescriptor]:
        """Return agents that advertise *capability*."""
        ...

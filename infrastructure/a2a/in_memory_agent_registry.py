"""InMemoryAgentRegistry — dict-backed agent discovery service.

Suitable for single-process testing and local development.
"""

from __future__ import annotations

from domain.entities.a2a import AgentDescriptor
from domain.ports.agent_registry import AgentRegistryPort
from domain.value_objects.agent_engine import AgentEngineType


class InMemoryAgentRegistry(AgentRegistryPort):
    """In-memory agent registry backed by a dict keyed on agent_id."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentDescriptor] = {}

    async def register(self, descriptor: AgentDescriptor) -> None:
        """Register or update an agent descriptor."""
        self._agents[descriptor.agent_id] = descriptor

    async def deregister(self, agent_id: str) -> None:
        """Remove an agent from the registry."""
        self._agents.pop(agent_id, None)

    async def lookup(self, agent_id: str) -> AgentDescriptor | None:
        """Look up a single agent by id."""
        return self._agents.get(agent_id)

    async def lookup_by_engine(self, engine: AgentEngineType) -> AgentDescriptor | None:
        """Look up an agent by engine type (returns first match)."""
        for desc in self._agents.values():
            if desc.engine_type == engine:
                return desc
        return None

    async def list_available(self) -> list[AgentDescriptor]:
        """Return all agents with status 'available'."""
        return [d for d in self._agents.values() if d.status == "available"]

    async def list_by_capability(self, capability: str) -> list[AgentDescriptor]:
        """Return agents that advertise *capability*."""
        return [d for d in self._agents.values() if d.has_capability(capability)]

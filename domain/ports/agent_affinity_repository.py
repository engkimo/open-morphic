"""AgentAffinityRepository port — persistence for engine-topic affinity scores.

Separate from SharedTaskStateRepository: different access patterns (engine×topic keyed
vs task_id keyed). Domain defines WHAT it needs. Infrastructure provides HOW.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.cognitive import AgentAffinityScore
from domain.value_objects.agent_engine import AgentEngineType


class AgentAffinityRepository(ABC):
    """Port for persisting and querying agent affinity scores."""

    @abstractmethod
    async def get(self, engine: AgentEngineType, topic: str) -> AgentAffinityScore | None:
        """Retrieve affinity for a specific engine-topic pair, or None."""
        ...

    @abstractmethod
    async def get_by_topic(self, topic: str) -> list[AgentAffinityScore]:
        """Retrieve all engine affinities for a given topic."""
        ...

    @abstractmethod
    async def get_by_engine(self, engine: AgentEngineType) -> list[AgentAffinityScore]:
        """Retrieve all topic affinities for a given engine."""
        ...

    @abstractmethod
    async def upsert(self, score: AgentAffinityScore) -> None:
        """Create or update an affinity score."""
        ...

    @abstractmethod
    async def list_all(self) -> list[AgentAffinityScore]:
        """Retrieve all affinity scores."""
        ...

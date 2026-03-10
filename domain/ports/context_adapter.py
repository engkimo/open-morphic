"""ContextAdapterPort — bidirectional context translation per engine.

Each agent engine speaks a different "context language".
Adapters translate: UCL → engine-specific format (inject) and engine output → insights (extract).

Analogous to OS device drivers: kernel has unified I/O, each driver translates to hardware protocol.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from domain.entities.cognitive import SharedTaskState
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.cognitive import CognitiveMemoryType


@dataclass(frozen=True)
class AdapterInsight:
    """A single insight extracted from engine output by a context adapter."""

    content: str
    memory_type: CognitiveMemoryType
    confidence: float = 0.5
    tags: list[str] = field(default_factory=list)


class ContextAdapterPort(ABC):
    """Port for bidirectional context translation between UCL and an agent engine."""

    @abstractmethod
    def engine_type(self) -> AgentEngineType:
        """Return which engine this adapter serves."""
        ...

    @abstractmethod
    def inject_context(
        self,
        state: SharedTaskState,
        memory_context: str,
        max_tokens: int = 2000,
    ) -> str:
        """Translate UCL shared state + memory into engine-specific context string.

        Args:
            state: Cross-agent task state (decisions, artifacts, blockers, history).
            memory_context: Pre-compressed memory string from ContextZipper or similar.
            max_tokens: Approximate token budget for the output string.

        Returns:
            Engine-formatted context string ready to inject.
        """
        ...

    @abstractmethod
    def extract_insights(
        self,
        output: str,
    ) -> list[AdapterInsight]:
        """Extract structured insights from raw engine execution output.

        Args:
            output: Raw text output from the agent engine.

        Returns:
            List of extracted insights with memory type classification.
        """
        ...

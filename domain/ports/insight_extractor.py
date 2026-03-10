"""InsightExtractorPort — extract structured insights from agent output.

Domain defines WHAT it needs. Infrastructure provides HOW.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.cognitive import CognitiveMemoryType


@dataclass
class ExtractedInsight:
    """A single insight extracted from agent execution output."""

    content: str
    memory_type: CognitiveMemoryType
    confidence: float = 0.5
    source_engine: AgentEngineType = AgentEngineType.OLLAMA
    tags: list[str] = field(default_factory=list)


class InsightExtractorPort(ABC):
    """Port for extracting structured insights from agent output."""

    @abstractmethod
    async def extract_from_output(
        self,
        engine: AgentEngineType,
        output: str,
    ) -> list[ExtractedInsight]:
        """Extract insights from raw agent execution output."""
        ...

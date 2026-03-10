"""Insight extractor — connects context adapters to the extraction pipeline.

Implements :class:`InsightExtractorPort`.
"""

from __future__ import annotations

from domain.ports.context_adapter import ContextAdapterPort
from domain.ports.insight_extractor import ExtractedInsight, InsightExtractorPort
from domain.services.memory_classifier import MemoryClassifier
from domain.value_objects.agent_engine import AgentEngineType


class InsightExtractor(InsightExtractorPort):
    """Extract insights from agent output via engine-specific adapters."""

    def __init__(
        self,
        adapters: dict[AgentEngineType, ContextAdapterPort],
    ) -> None:
        self._adapters = adapters

    async def extract_from_output(
        self,
        engine: AgentEngineType,
        output: str,
    ) -> list[ExtractedInsight]:
        adapter = self._adapters.get(engine)
        if adapter is None or not output or not output.strip():
            return []

        raw_insights = adapter.extract_insights(output)
        if not raw_insights:
            return []

        # Deduplicate by normalised content
        seen: set[str] = set()
        unique = []
        for ins in raw_insights:
            key = ins.content.strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(ins)

        # Map AdapterInsight -> ExtractedInsight, optionally reclassify
        results: list[ExtractedInsight] = []
        for ai in unique:
            memory_type = ai.memory_type
            confidence = ai.confidence

            if confidence < 0.5:
                classified_type, classified_conf = MemoryClassifier.classify_with_confidence(
                    ai.content
                )
                memory_type = classified_type
                confidence = classified_conf

            results.append(
                ExtractedInsight(
                    content=ai.content,
                    memory_type=memory_type,
                    confidence=confidence,
                    source_engine=engine,
                    tags=list(ai.tags),
                )
            )

        return results

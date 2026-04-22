"""Insight extractor — connects context adapters to the extraction pipeline.

Implements :class:`InsightExtractorPort`.
"""

from __future__ import annotations

from domain.ports.context_adapter import AdapterInsight, ContextAdapterPort
from domain.ports.embedding import EmbeddingPort
from domain.ports.insight_extractor import ExtractedInsight, InsightExtractorPort
from domain.ports.memory_classifier import MemoryClassifierPort
from domain.services.memory_classifier import MemoryClassifier
from domain.services.semantic_fingerprint import SemanticFingerprint
from domain.value_objects.agent_engine import AgentEngineType


class InsightExtractor(InsightExtractorPort):
    """Extract insights from agent output via engine-specific adapters."""

    def __init__(
        self,
        adapters: dict[AgentEngineType, ContextAdapterPort],
        embedding_port: EmbeddingPort | None = None,
        memory_classifier: MemoryClassifierPort | None = None,
        semantic_dedup_threshold: float = 0.85,
        token_dedup_threshold: float = 0.6,
    ) -> None:
        self._adapters = adapters
        self._embedding_port = embedding_port
        self._memory_classifier = memory_classifier
        self._dedup_threshold = semantic_dedup_threshold
        self._token_dedup_threshold = token_dedup_threshold

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

        # Deduplicate: semantic if embedding available, else exact-match + token overlap
        if self._embedding_port:
            unique = await self._semantic_dedup(raw_insights)
        else:
            unique = self._exact_dedup(raw_insights)
            unique = self._token_dedup(unique)

        # Map AdapterInsight -> ExtractedInsight, optionally reclassify
        results: list[ExtractedInsight] = []
        for ai in unique:
            memory_type = ai.memory_type
            confidence = ai.confidence

            if confidence < 0.5:
                if self._memory_classifier is not None:
                    classified_type, classified_conf = self._memory_classifier.classify(ai.content)
                else:
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

    @staticmethod
    def _exact_dedup(insights: list[AdapterInsight]) -> list[AdapterInsight]:
        """Deduplicate by normalised content (case-insensitive, stripped)."""
        seen: set[str] = set()
        unique: list[AdapterInsight] = []
        for ins in insights:
            key = ins.content.strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(ins)
        return unique

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Tokenize text into a set of normalised words (lowercase, no punctuation)."""
        import re

        return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w}

    def _token_dedup(self, insights: list[AdapterInsight]) -> list[AdapterInsight]:
        """Deduplicate using word-level Jaccard similarity.

        Catches paraphrases that share most words but differ in phrasing.
        Applied after exact-match dedup when no embedding port is available.
        """
        if len(insights) <= 1:
            return insights

        drop: set[int] = set()
        n = len(insights)

        for i in range(n):
            if i in drop:
                continue
            tokens_i = self._tokenize(insights[i].content)
            if not tokens_i:
                continue
            for j in range(i + 1, n):
                if j in drop:
                    continue
                tokens_j = self._tokenize(insights[j].content)
                if not tokens_j:
                    continue
                intersection = len(tokens_i & tokens_j)
                union = len(tokens_i | tokens_j)
                if union > 0 and intersection / union >= self._token_dedup_threshold:
                    # Keep higher-confidence one
                    if insights[i].confidence >= insights[j].confidence:
                        drop.add(j)
                    else:
                        drop.add(i)
                        break
        return [ins for idx, ins in enumerate(insights) if idx not in drop]

    @staticmethod
    def jaccard_similarity(text_a: str, text_b: str) -> float:
        """Compute Jaccard similarity between two texts (word-level, punctuation-free)."""
        tokens_a = InsightExtractor._tokenize(text_a)
        tokens_b = InsightExtractor._tokenize(text_b)
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)
        return intersection / union if union > 0 else 0.0

    async def _semantic_dedup(self, insights: list[AdapterInsight]) -> list[AdapterInsight]:
        """Deduplicate using embedding cosine similarity.

        For each pair with similarity >= threshold, keep the higher-confidence one.
        Falls back to exact-match if embedding fails.
        """
        # Filter empty content first
        non_empty = [ins for ins in insights if ins.content.strip()]
        if not non_empty:
            return []

        assert self._embedding_port is not None

        try:
            vectors = await self._embedding_port.embed([ins.content for ins in non_empty])
        except Exception:
            # Graceful degradation: fall back to exact-match
            return self._exact_dedup(insights)

        # Mark which indices to drop (absorbed by a higher-confidence duplicate)
        n = len(non_empty)
        drop: set[int] = set()

        for i in range(n):
            if i in drop:
                continue
            for j in range(i + 1, n):
                if j in drop:
                    continue
                sim = SemanticFingerprint.cosine_similarity(vectors[i], vectors[j])
                if sim >= self._dedup_threshold:
                    # Drop the lower-confidence one
                    if non_empty[i].confidence >= non_empty[j].confidence:
                        drop.add(j)
                    else:
                        drop.add(i)
                        break  # i is dropped, move to next i

        return [ins for idx, ins in enumerate(non_empty) if idx not in drop]

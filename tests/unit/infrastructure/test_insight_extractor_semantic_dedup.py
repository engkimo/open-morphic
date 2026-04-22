"""Tests for InsightExtractor semantic deduplication (Sprint 11.1)."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from domain.ports.context_adapter import AdapterInsight, ContextAdapterPort
from domain.ports.embedding import EmbeddingPort
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.cognitive import CognitiveMemoryType
from infrastructure.cognitive.insight_extractor import InsightExtractor

# ── Helpers ──


class FakeEmbeddingPort(EmbeddingPort):
    """Deterministic fake: similar texts get similar vectors."""

    def __init__(self, dims: int = 384) -> None:
        self._dims = dims

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._text_to_vec(t) for t in texts]

    def dimensions(self) -> int:
        return self._dims

    def _text_to_vec(self, text: str) -> list[float]:
        """Normalised text → deterministic vector. Similar strings get similar vectors."""
        seed = sum(ord(c) for c in text.strip().lower()) % (2**31)
        rng = np.random.default_rng(seed)
        return list(rng.standard_normal(self._dims))


class HighSimilarityEmbeddingPort(EmbeddingPort):
    """Returns identical vectors for paraphrased texts (simulates real embeddings)."""

    def __init__(self, similar_groups: list[list[int]], dims: int = 384) -> None:
        """similar_groups: list of index groups that should have identical vectors."""
        self._dims = dims
        self._similar_groups = similar_groups

    async def embed(self, texts: list[str]) -> list[list[float]]:
        rng = np.random.default_rng(42)
        # Start with unique vectors
        vectors = [list(rng.standard_normal(self._dims)) for _ in texts]
        # Make similar groups share the same vector
        for group in self._similar_groups:
            base = vectors[group[0]]
            for idx in group[1:]:
                vectors[idx] = list(base)
        return vectors

    def dimensions(self) -> int:
        return self._dims


class FailingEmbeddingPort(EmbeddingPort):
    """Always raises to test graceful degradation."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise ConnectionError("Ollama unavailable")

    def dimensions(self) -> int:
        return 384


def _adapter(
    insights: list[AdapterInsight] | None = None,
) -> ContextAdapterPort:
    mock = MagicMock(spec=ContextAdapterPort)
    mock.extract_insights.return_value = insights or []
    return mock


def _ai(
    content: str = "fact",
    mem_type: CognitiveMemoryType = CognitiveMemoryType.SEMANTIC,
    confidence: float = 0.7,
    tags: list[str] | None = None,
) -> AdapterInsight:
    return AdapterInsight(
        content=content,
        memory_type=mem_type,
        confidence=confidence,
        tags=tags or [],
    )


# ── Tests ──


class TestSemanticDedup:
    """InsightExtractor with EmbeddingPort for semantic deduplication."""

    @pytest.mark.anyio
    async def test_exact_duplicates_removed(self) -> None:
        """Identical content is detected via embedding similarity."""
        adapter = _adapter(
            [
                _ai("Created file config.yaml", confidence=0.8),
                _ai("Created file config.yaml", confidence=0.6),
            ]
        )
        ext = InsightExtractor(
            adapters={AgentEngineType.CLAUDE_CODE: adapter},
            embedding_port=FakeEmbeddingPort(),
        )
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "output")
        assert len(results) == 1
        assert results[0].confidence == 0.8  # Higher confidence kept

    @pytest.mark.anyio
    async def test_paraphrased_duplicates_removed(self) -> None:
        """Paraphrased facts are detected as duplicates via embedding similarity."""
        adapter = _adapter(
            [
                _ai("Created file: config.yaml", confidence=0.8),
                _ai("File config.yaml created", confidence=0.6),
                _ai("Completely different topic about Redis", confidence=0.7),
            ]
        )
        # Indices 0 and 1 are paraphrases → same vector group
        embedding = HighSimilarityEmbeddingPort(similar_groups=[[0, 1]])
        ext = InsightExtractor(
            adapters={AgentEngineType.CLAUDE_CODE: adapter},
            embedding_port=embedding,
            semantic_dedup_threshold=0.85,
        )
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "output")
        assert len(results) == 2
        contents = {r.content for r in results}
        assert "Completely different topic about Redis" in contents

    @pytest.mark.anyio
    async def test_unique_insights_preserved(self) -> None:
        """Distinct insights survive dedup."""
        adapter = _adapter(
            [
                _ai("Uses PostgreSQL for database"),
                _ai("Decided to use FastAPI"),
                _ai("Error: connection refused"),
            ]
        )
        ext = InsightExtractor(
            adapters={AgentEngineType.CLAUDE_CODE: adapter},
            embedding_port=FakeEmbeddingPort(),
        )
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "output")
        assert len(results) == 3

    @pytest.mark.anyio
    async def test_higher_confidence_kept(self) -> None:
        """When paraphrases are deduped, the higher-confidence one is kept."""
        adapter = _adapter(
            [
                _ai("config.yaml created successfully", confidence=0.5),
                _ai("Created the config.yaml file", confidence=0.9),
            ]
        )
        embedding = HighSimilarityEmbeddingPort(similar_groups=[[0, 1]])
        ext = InsightExtractor(
            adapters={AgentEngineType.CLAUDE_CODE: adapter},
            embedding_port=embedding,
        )
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "output")
        assert len(results) == 1
        assert results[0].confidence >= 0.9

    @pytest.mark.anyio
    async def test_embedding_failure_fallback_to_exact(self) -> None:
        """If embedding fails, falls back to exact-match dedup."""
        adapter = _adapter(
            [
                _ai("Uses Redis"),
                _ai("uses redis"),  # exact-match dup (case insensitive)
                _ai("Different content"),
            ]
        )
        ext = InsightExtractor(
            adapters={AgentEngineType.CLAUDE_CODE: adapter},
            embedding_port=FailingEmbeddingPort(),
        )
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "output")
        assert len(results) == 2

    @pytest.mark.anyio
    async def test_no_embedding_port_uses_exact_dedup(self) -> None:
        """Without embedding port, exact-match dedup is used (backward compat)."""
        adapter = _adapter(
            [
                _ai("Uses Redis"),
                _ai("uses redis"),
            ]
        )
        ext = InsightExtractor(
            adapters={AgentEngineType.CLAUDE_CODE: adapter},
            embedding_port=None,
        )
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "output")
        assert len(results) == 1

    @pytest.mark.anyio
    async def test_empty_content_filtered(self) -> None:
        """Empty-content insights are filtered before embedding."""
        adapter = _adapter(
            [
                _ai("", confidence=0.7),
                _ai("real content", confidence=0.7),
            ]
        )
        ext = InsightExtractor(
            adapters={AgentEngineType.CLAUDE_CODE: adapter},
            embedding_port=FakeEmbeddingPort(),
        )
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "output")
        assert len(results) == 1
        assert results[0].content == "real content"

    @pytest.mark.anyio
    async def test_custom_threshold(self) -> None:
        """Custom dedup threshold is respected."""
        adapter = _adapter(
            [
                _ai("Created file: config.yaml", confidence=0.8),
                _ai("File config.yaml created", confidence=0.6),
            ]
        )
        embedding = HighSimilarityEmbeddingPort(similar_groups=[[0, 1]])
        ext = InsightExtractor(
            adapters={AgentEngineType.CLAUDE_CODE: adapter},
            embedding_port=embedding,
            semantic_dedup_threshold=0.5,  # loose threshold
        )
        results = await ext.extract_from_output(
            AgentEngineType.CLAUDE_CODE,
            "output",
        )
        assert len(results) == 1  # deduped

    @pytest.mark.anyio
    async def test_three_way_dedup(self) -> None:
        """Three paraphrases → only one survives."""
        adapter = _adapter(
            [
                _ai("File created: config.yaml", confidence=0.6),
                _ai("Created file config.yaml", confidence=0.9),
                _ai("config.yaml was created", confidence=0.5),
            ]
        )
        embedding = HighSimilarityEmbeddingPort(similar_groups=[[0, 1, 2]])
        ext = InsightExtractor(
            adapters={AgentEngineType.CLAUDE_CODE: adapter},
            embedding_port=embedding,
        )
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "output")
        assert len(results) == 1
        assert results[0].confidence == 0.9  # Highest confidence kept


class TestTokenDedup:
    """InsightExtractor token-overlap dedup (no embedding port)."""

    @pytest.mark.anyio
    async def test_paraphrased_deduped_by_token_overlap(self) -> None:
        """Paraphrases sharing most words are deduped via Jaccard similarity."""
        # "decided to use postgresql for the database layer" vs
        # "postgresql was chosen as the database backend"
        # Shared: {postgresql, the, database} = 3, Union ~10 → Jaccard ~0.3
        adapter = _adapter(
            [
                _ai("Decided to use PostgreSQL for the database layer", confidence=0.8),
                _ai("PostgreSQL was chosen as the database backend", confidence=0.6),
            ]
        )
        ext = InsightExtractor(
            adapters={AgentEngineType.CLAUDE_CODE: adapter},
            embedding_port=None,
            token_dedup_threshold=0.25,  # Shared ~3/10 = 0.3 → matches
        )
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "output")
        assert len(results) == 1
        assert results[0].confidence == 0.8  # Higher confidence kept

    @pytest.mark.anyio
    async def test_distinct_texts_preserved(self) -> None:
        """Texts with low word overlap are kept separate."""
        adapter = _adapter(
            [
                _ai("Decided to use PostgreSQL for the database layer.", confidence=0.8),
                _ai("Also decided to use Redis for caching.", confidence=0.7),
            ]
        )
        ext = InsightExtractor(
            adapters={AgentEngineType.CLAUDE_CODE: adapter},
            embedding_port=None,
            token_dedup_threshold=0.6,
        )
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "output")
        assert len(results) == 2

    @pytest.mark.anyio
    async def test_token_dedup_keeps_higher_confidence(self) -> None:
        """When overlap detected, the higher-confidence insight is kept."""
        adapter = _adapter(
            [
                _ai("Created file config.yaml with settings.", confidence=0.5),
                _ai("The config.yaml file was created with settings.", confidence=0.9),
            ]
        )
        ext = InsightExtractor(
            adapters={AgentEngineType.CLAUDE_CODE: adapter},
            embedding_port=None,
            token_dedup_threshold=0.4,
        )
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "output")
        assert len(results) == 1
        assert results[0].confidence == 0.9

    @pytest.mark.anyio
    async def test_token_dedup_three_way(self) -> None:
        """Three paraphrases with high word overlap → one survives."""
        # All share {connection, refused, port, 5432} and optionally {error, to, was}
        # Jaccard between pairs ≈ 0.5-0.7
        adapter = _adapter(
            [
                _ai("connection refused on port 5432 error", confidence=0.6),
                _ai("connection to port 5432 was refused", confidence=0.7),
                _ai("port 5432 connection refused error", confidence=0.5),
            ]
        )
        ext = InsightExtractor(
            adapters={AgentEngineType.CLAUDE_CODE: adapter},
            embedding_port=None,
            token_dedup_threshold=0.4,
        )
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "output")
        assert len(results) == 1
        assert results[0].confidence == 0.7

    @pytest.mark.anyio
    async def test_custom_threshold_strict(self) -> None:
        """Strict threshold keeps more items."""
        adapter = _adapter(
            [
                _ai("Decided to use PostgreSQL for the database layer."),
                _ai("PostgreSQL was chosen as the database backend."),
            ]
        )
        ext = InsightExtractor(
            adapters={AgentEngineType.CLAUDE_CODE: adapter},
            embedding_port=None,
            token_dedup_threshold=0.9,  # Very strict — most paraphrases kept
        )
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "output")
        assert len(results) == 2  # Not enough overlap at 0.9

    @pytest.mark.anyio
    async def test_single_insight_no_dedup(self) -> None:
        """Single insight passes through without dedup attempt."""
        adapter = _adapter([_ai("Only one insight here.")])
        ext = InsightExtractor(
            adapters={AgentEngineType.CLAUDE_CODE: adapter},
            embedding_port=None,
            token_dedup_threshold=0.3,
        )
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "output")
        assert len(results) == 1


class TestJaccardSimilarity:
    """Unit tests for InsightExtractor.jaccard_similarity static method."""

    def test_identical_texts(self) -> None:
        assert InsightExtractor.jaccard_similarity("hello world", "hello world") == 1.0

    def test_no_overlap(self) -> None:
        assert InsightExtractor.jaccard_similarity("hello world", "foo bar") == 0.0

    def test_partial_overlap(self) -> None:
        sim = InsightExtractor.jaccard_similarity(
            "decided to use postgresql", "postgresql was chosen"
        )
        # {decided, to, use, postgresql} ∩ {postgresql, was, chosen} = {postgresql} → 1/6
        assert 0.1 <= sim <= 0.2

    def test_case_insensitive(self) -> None:
        assert InsightExtractor.jaccard_similarity("Hello World", "hello world") == 1.0

    def test_empty_string(self) -> None:
        assert InsightExtractor.jaccard_similarity("", "hello") == 0.0
        assert InsightExtractor.jaccard_similarity("hello", "") == 0.0
        assert InsightExtractor.jaccard_similarity("", "") == 0.0

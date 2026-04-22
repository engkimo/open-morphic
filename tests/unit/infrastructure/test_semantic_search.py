"""Tests for SemanticBucketStore, OllamaEmbeddingAdapter, and vector-search repos.

Infrastructure layer tests — mocked httpx for Ollama, pure in-memory bucket store,
and InMemoryMemoryRepository with embedding-based search.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from domain.entities.memory import MemoryEntry
from domain.ports.embedding import EmbeddingPort
from domain.services.semantic_fingerprint import SemanticFingerprint
from domain.value_objects.status import MemoryType
from infrastructure.memory.embedding_adapters import OllamaEmbeddingAdapter
from infrastructure.memory.semantic_fingerprint import SemanticBucketStore
from infrastructure.persistence.in_memory import InMemoryMemoryRepository

# ── Helpers ──


class FakeEmbeddingPort(EmbeddingPort):
    """Deterministic fake for testing. Maps text to a hash-seeded vector."""

    def __init__(self, dims: int = 384) -> None:
        self._dims = dims

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._text_to_vec(t) for t in texts]

    def dimensions(self) -> int:
        return self._dims

    def _text_to_vec(self, text: str) -> list[float]:
        seed = sum(ord(c) for c in text) % (2**31)
        rng = np.random.default_rng(seed)
        return list(rng.standard_normal(self._dims))


# ── SemanticBucketStore Tests ──


class TestSemanticBucketStore:
    """In-memory LSH-bucketed store for near-O(1) semantic retrieval."""

    def _make_store(self, dims: int = 384, n_planes: int = 16) -> SemanticBucketStore:
        fp = SemanticFingerprint(dimensions=dims, n_planes=n_planes, seed=42)
        return SemanticBucketStore(fingerprint=fp)

    def test_add_and_find_exact(self) -> None:
        store = self._make_store(dims=4, n_planes=8)
        vec = [1.0, 2.0, 3.0, 4.0]
        store.add("mem-1", vec)
        results = store.find_similar(vec, top_k=1, threshold=0.9)
        assert len(results) == 1
        assert results[0][0] == "mem-1"
        assert results[0][1] == pytest.approx(1.0)

    def test_find_returns_sorted_by_similarity(self) -> None:
        store = self._make_store(dims=4, n_planes=8)
        store.add("a", [1.0, 0.0, 0.0, 0.0])
        store.add("b", [0.9, 0.1, 0.0, 0.0])
        store.add("c", [0.0, 1.0, 0.0, 0.0])
        results = store.find_similar([1.0, 0.0, 0.0, 0.0], top_k=3, threshold=0.0)
        ids = [r[0] for r in results]
        # "a" is exact match, "b" is close, "c" is orthogonal
        assert ids[0] == "a"

    def test_threshold_filters_low_similarity(self) -> None:
        store = self._make_store(dims=4, n_planes=8)
        store.add("close", [1.0, 0.0, 0.0, 0.0])
        store.add("far", [0.0, 0.0, 0.0, 1.0])
        results = store.find_similar([1.0, 0.0, 0.0, 0.0], top_k=10, threshold=0.9)
        ids = [r[0] for r in results]
        assert "close" in ids
        assert "far" not in ids

    def test_top_k_limits_results(self) -> None:
        store = self._make_store(dims=4, n_planes=8)
        for i in range(10):
            store.add(f"mem-{i}", [float(i), 1.0, 1.0, 1.0])
        results = store.find_similar([5.0, 1.0, 1.0, 1.0], top_k=3, threshold=0.0)
        assert len(results) <= 3

    def test_remove_entry(self) -> None:
        store = self._make_store(dims=4, n_planes=8)
        vec = [1.0, 2.0, 3.0, 4.0]
        store.add("mem-1", vec)
        store.remove("mem-1")
        results = store.find_similar(vec, top_k=5, threshold=0.0)
        ids = [r[0] for r in results]
        assert "mem-1" not in ids

    def test_empty_store_returns_empty(self) -> None:
        store = self._make_store(dims=4, n_planes=8)
        results = store.find_similar([1.0, 0.0, 0.0, 0.0], top_k=5, threshold=0.0)
        assert results == []

    def test_multi_probe_finds_nearby_buckets(self) -> None:
        """Multi-probe: flip bits to search neighboring buckets."""
        store = self._make_store(dims=384, n_planes=16)
        rng = np.random.default_rng(42)
        base = list(rng.standard_normal(384))
        store.add("base", base)

        # Slightly different vector (may land in different bucket)
        noisy = list(np.array(base) + rng.standard_normal(384) * 0.1)
        # With multi_probe_bits=2, should still find "base"
        results = store.find_similar(noisy, top_k=5, threshold=0.5, multi_probe_bits=2)
        ids = [r[0] for r in results]
        assert "base" in ids

    def test_count_property(self) -> None:
        store = self._make_store(dims=4, n_planes=8)
        assert store.count == 0
        store.add("a", [1.0, 0.0, 0.0, 0.0])
        store.add("b", [0.0, 1.0, 0.0, 0.0])
        assert store.count == 2
        store.remove("a")
        assert store.count == 1

    def test_duplicate_id_overwrites(self) -> None:
        store = self._make_store(dims=4, n_planes=8)
        store.add("a", [1.0, 0.0, 0.0, 0.0])
        store.add("a", [0.0, 1.0, 0.0, 0.0])
        assert store.count == 1
        results = store.find_similar([0.0, 1.0, 0.0, 0.0], top_k=1, threshold=0.9)
        assert len(results) == 1
        assert results[0][0] == "a"


# ── OllamaEmbeddingAdapter Tests ──


class TestOllamaEmbeddingAdapter:
    """Tests for Ollama HTTP embedding adapter."""

    def test_dimensions_matches_config(self) -> None:
        adapter = OllamaEmbeddingAdapter(
            base_url="http://localhost:11434",
            model="all-minilm",
            dimensions=384,
        )
        assert adapter.dimensions() == 384

    @pytest.mark.asyncio
    async def test_embed_single_text(self) -> None:
        fake_embedding = list(np.random.default_rng(1).standard_normal(384))

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {"embeddings": [fake_embedding]}  # sync method
        mock_response.raise_for_status = lambda: None  # sync method

        with patch("infrastructure.memory.embedding_adapters.httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.post.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = instance

            adapter = OllamaEmbeddingAdapter(
                base_url="http://localhost:11434",
                model="all-minilm",
                dimensions=384,
            )
            result = await adapter.embed(["hello world"])

            assert len(result) == 1
            assert len(result[0]) == 384
            instance.post.assert_called_once()
            call_kwargs = instance.post.call_args
            assert call_kwargs[0][0] == "http://localhost:11434/api/embed"

    @pytest.mark.asyncio
    async def test_embed_multiple_texts(self) -> None:
        rng = np.random.default_rng(2)
        fake_embeddings = [list(rng.standard_normal(384)) for _ in range(3)]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {"embeddings": fake_embeddings}
        mock_response.raise_for_status = lambda: None

        with patch("infrastructure.memory.embedding_adapters.httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.post.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = instance

            adapter = OllamaEmbeddingAdapter(
                base_url="http://localhost:11434",
                model="all-minilm",
                dimensions=384,
            )
            result = await adapter.embed(["one", "two", "three"])

            assert len(result) == 3
            for emb in result:
                assert len(emb) == 384

    @pytest.mark.asyncio
    async def test_embed_empty_list_returns_empty(self) -> None:
        adapter = OllamaEmbeddingAdapter(
            base_url="http://localhost:11434",
            model="all-minilm",
            dimensions=384,
        )
        result = await adapter.embed([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_http_error_raises(self) -> None:
        def raise_error() -> None:
            raise Exception("Ollama unavailable")

        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.raise_for_status = raise_error

        with patch("infrastructure.memory.embedding_adapters.httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.post.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = instance

            adapter = OllamaEmbeddingAdapter(
                base_url="http://localhost:11434",
                model="all-minilm",
                dimensions=384,
            )
            with pytest.raises(Exception, match="Ollama unavailable"):
                await adapter.embed(["test"])


# ── InMemoryMemoryRepository with Embedding Tests ──


class TestInMemoryRepoVectorSearch:
    """InMemoryMemoryRepository: semantic search when embedding_port is provided."""

    @pytest.fixture()
    def fake_embedder(self) -> FakeEmbeddingPort:
        return FakeEmbeddingPort(dims=384)

    @pytest.fixture()
    def repo_with_embeddings(self, fake_embedder: FakeEmbeddingPort) -> InMemoryMemoryRepository:
        return InMemoryMemoryRepository(embedding_port=fake_embedder)

    @pytest.fixture()
    def repo_without_embeddings(self) -> InMemoryMemoryRepository:
        return InMemoryMemoryRepository()

    def _make_entry(self, content: str) -> MemoryEntry:
        return MemoryEntry(content=content, memory_type=MemoryType.L2_SEMANTIC)

    @pytest.mark.asyncio
    async def test_search_without_embedding_falls_back_to_keyword(
        self, repo_without_embeddings: InMemoryMemoryRepository
    ) -> None:
        """No embedding_port → keyword search (backward compat)."""
        await repo_without_embeddings.add(self._make_entry("Python programming language"))
        results = await repo_without_embeddings.search("Python")
        assert len(results) == 1
        assert "Python" in results[0].content

    @pytest.mark.asyncio
    async def test_search_with_embedding_uses_vectors(
        self, repo_with_embeddings: InMemoryMemoryRepository
    ) -> None:
        """With embedding_port → vector search finds entries."""
        await repo_with_embeddings.add(self._make_entry("Python programming language"))
        await repo_with_embeddings.add(self._make_entry("JavaScript web development"))
        results = await repo_with_embeddings.search("Python programming language")
        assert len(results) >= 1
        # Exact content match should have highest similarity
        assert results[0].content == "Python programming language"

    @pytest.mark.asyncio
    async def test_vector_search_respects_top_k(
        self, repo_with_embeddings: InMemoryMemoryRepository
    ) -> None:
        for i in range(10):
            await repo_with_embeddings.add(self._make_entry(f"entry number {i}"))
        results = await repo_with_embeddings.search("entry number 5", top_k=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_keyword_search_still_works(
        self, repo_without_embeddings: InMemoryMemoryRepository
    ) -> None:
        """Original keyword search remains functional."""
        await repo_without_embeddings.add(self._make_entry("hello world"))
        await repo_without_embeddings.add(self._make_entry("goodbye world"))
        results = await repo_without_embeddings.search("hello")
        assert len(results) == 1
        assert results[0].content == "hello world"

    @pytest.mark.asyncio
    async def test_add_and_delete_with_embeddings(
        self, repo_with_embeddings: InMemoryMemoryRepository
    ) -> None:
        entry = self._make_entry("to be deleted")
        await repo_with_embeddings.add(entry)
        await repo_with_embeddings.delete(entry.id)
        results = await repo_with_embeddings.search("to be deleted")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_empty_repo_returns_empty(
        self, repo_with_embeddings: InMemoryMemoryRepository
    ) -> None:
        results = await repo_with_embeddings.search("anything")
        assert results == []

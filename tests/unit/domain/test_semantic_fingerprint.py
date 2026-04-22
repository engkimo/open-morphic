"""Tests for SemanticFingerprint domain service — LSH hash + cosine similarity.

Pure domain logic — no I/O, no external deps beyond numpy.
"""

from __future__ import annotations

import numpy as np
import pytest

from domain.services.semantic_fingerprint import SemanticFingerprint


class TestCosineSimility:
    """cosine_similarity: pure vector math."""

    def test_identical_vectors_return_one(self) -> None:
        fp = SemanticFingerprint(dimensions=4, n_planes=8, seed=42)
        v = [1.0, 2.0, 3.0, 4.0]
        assert fp.cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_return_zero(self) -> None:
        fp = SemanticFingerprint(dimensions=2, n_planes=8, seed=42)
        assert fp.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_return_negative_one(self) -> None:
        fp = SemanticFingerprint(dimensions=3, n_planes=8, seed=42)
        v = [1.0, 2.0, 3.0]
        neg_v = [-1.0, -2.0, -3.0]
        assert fp.cosine_similarity(v, neg_v) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self) -> None:
        fp = SemanticFingerprint(dimensions=3, n_planes=8, seed=42)
        assert fp.cosine_similarity([0.0, 0.0, 0.0], [1.0, 2.0, 3.0]) == pytest.approx(0.0)

    def test_similar_vectors_high_score(self) -> None:
        fp = SemanticFingerprint(dimensions=3, n_planes=8, seed=42)
        v1 = [1.0, 2.0, 3.0]
        v2 = [1.1, 2.1, 2.9]
        assert fp.cosine_similarity(v1, v2) > 0.99


class TestLSHHash:
    """lsh_hash: locality-sensitive hashing via random hyperplanes."""

    def test_deterministic_same_seed(self) -> None:
        fp1 = SemanticFingerprint(dimensions=384, n_planes=32, seed=42)
        fp2 = SemanticFingerprint(dimensions=384, n_planes=32, seed=42)
        vec = list(np.random.default_rng(99).standard_normal(384))
        assert fp1.lsh_hash(vec) == fp2.lsh_hash(vec)

    def test_different_seeds_different_hash(self) -> None:
        fp1 = SemanticFingerprint(dimensions=384, n_planes=32, seed=42)
        fp2 = SemanticFingerprint(dimensions=384, n_planes=32, seed=99)
        vec = list(np.random.default_rng(99).standard_normal(384))
        # Extremely unlikely to be the same with different random planes
        assert fp1.lsh_hash(vec) != fp2.lsh_hash(vec)

    def test_hash_is_hex_string(self) -> None:
        fp = SemanticFingerprint(dimensions=4, n_planes=16, seed=42)
        h = fp.lsh_hash([1.0, 2.0, 3.0, 4.0])
        assert isinstance(h, str)
        # Should be valid hex
        int(h, 16)

    def test_similar_vectors_same_hash(self) -> None:
        """Nearby vectors should often get the same LSH bucket."""
        fp = SemanticFingerprint(dimensions=384, n_planes=16, seed=42)
        rng = np.random.default_rng(123)
        base = rng.standard_normal(384)
        # Add tiny noise
        noisy = base + rng.standard_normal(384) * 0.01
        assert fp.lsh_hash(list(base)) == fp.lsh_hash(list(noisy))

    def test_distant_vectors_different_hash(self) -> None:
        """Distant vectors should (very likely) get different LSH buckets."""
        fp = SemanticFingerprint(dimensions=384, n_planes=32, seed=42)
        rng = np.random.default_rng(456)
        v1 = list(rng.standard_normal(384))
        v2 = list(-np.array(v1))  # Opposite direction
        assert fp.lsh_hash(v1) != fp.lsh_hash(v2)

    def test_n_planes_affects_granularity(self) -> None:
        """More planes = more bits = finer granularity (longer hex)."""
        fp8 = SemanticFingerprint(dimensions=4, n_planes=8, seed=42)
        fp32 = SemanticFingerprint(dimensions=4, n_planes=32, seed=42)
        v = [1.0, 2.0, 3.0, 4.0]
        h8 = fp8.lsh_hash(v)
        h32 = fp32.lsh_hash(v)
        # 32-bit hash should be longer hex than 8-bit hash
        assert len(h32) >= len(h8)

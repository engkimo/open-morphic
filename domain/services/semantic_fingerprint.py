"""SemanticFingerprint — LSH hashing + cosine similarity for semantic memory.

Pure domain service: no I/O, no external deps beyond numpy.
Uses Locality-Sensitive Hashing (LSH) via random hyperplanes to produce
semantic-aware hash codes. Similar vectors map to the same bucket with high probability.
"""

from __future__ import annotations

import numpy as np


class SemanticFingerprint:
    """Locality-Sensitive Hashing for semantic memory bucketing.

    Seeded RNG ensures deterministic hyperplanes across restarts (no file persistence).
    """

    def __init__(self, dimensions: int, n_planes: int = 32, seed: int = 42) -> None:
        self._dimensions = dimensions
        self._n_planes = n_planes
        rng = np.random.default_rng(seed)
        self._planes: np.ndarray = rng.standard_normal((n_planes, dimensions))

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def n_planes(self) -> int:
        return self._n_planes

    def lsh_hash(self, vector: list[float]) -> str:
        """Compute LSH hash: project vector onto random hyperplanes → binary code → hex."""
        arr = np.asarray(vector, dtype=np.float64)
        projections = self._planes @ arr
        bits = (projections > 0).astype(int)
        binary_str = "".join(str(b) for b in bits)
        return format(int(binary_str, 2), f"0{(self._n_planes + 3) // 4}x")

    @staticmethod
    def cosine_similarity(v1: list[float], v2: list[float]) -> float:
        """Compute cosine similarity between two vectors. Returns 0.0 for zero vectors."""
        a = np.asarray(v1, dtype=np.float64)
        b = np.asarray(v2, dtype=np.float64)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

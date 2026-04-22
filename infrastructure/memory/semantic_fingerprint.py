"""SemanticBucketStore — LSH-bucketed in-memory vector store.

Uses SemanticFingerprint (domain service) for hashing, provides
near-O(1) retrieval of semantically similar entries via bucket + multi-probe.
"""

from __future__ import annotations

from itertools import combinations

from domain.services.semantic_fingerprint import SemanticFingerprint


class SemanticBucketStore:
    """In-memory store with LSH bucketing for fast semantic retrieval.

    Entries are stored in buckets keyed by their LSH hash.
    find_similar() checks the query's bucket first (O(1)), then optionally
    probes neighboring buckets via bit-flipping (multi-probe LSH).
    """

    def __init__(self, fingerprint: SemanticFingerprint) -> None:
        self._fp = fingerprint
        self._buckets: dict[str, dict[str, list[float]]] = {}  # hash -> {id -> vector}
        self._id_to_hash: dict[str, str] = {}  # id -> hash (for O(1) removal)

    @property
    def count(self) -> int:
        return len(self._id_to_hash)

    def add(self, entry_id: str, vector: list[float]) -> str:
        """Add or overwrite an entry. Returns the LSH bucket hash."""
        # Remove old entry if exists (overwrite semantics)
        if entry_id in self._id_to_hash:
            self.remove(entry_id)

        bucket_hash = self._fp.lsh_hash(vector)
        if bucket_hash not in self._buckets:
            self._buckets[bucket_hash] = {}
        self._buckets[bucket_hash][entry_id] = vector
        self._id_to_hash[entry_id] = bucket_hash
        return bucket_hash

    def remove(self, entry_id: str) -> None:
        """Remove an entry by ID."""
        bucket_hash = self._id_to_hash.pop(entry_id, None)
        if bucket_hash is not None and bucket_hash in self._buckets:
            self._buckets[bucket_hash].pop(entry_id, None)
            if not self._buckets[bucket_hash]:
                del self._buckets[bucket_hash]

    def find_similar(
        self,
        vector: list[float],
        top_k: int = 5,
        threshold: float = 0.5,
        multi_probe_bits: int = 1,
    ) -> list[tuple[str, float]]:
        """Find entries similar to vector. Returns [(id, similarity), ...] sorted desc.

        Args:
            vector: Query vector.
            top_k: Max results.
            threshold: Minimum cosine similarity.
            multi_probe_bits: Number of bits to flip for neighboring bucket probes.
                0 = exact bucket only, 1 = flip each bit individually, 2 = flip pairs, etc.
        """
        query_hash = self._fp.lsh_hash(vector)

        # Collect candidate entries from the query bucket + neighboring buckets
        candidate_hashes = {query_hash}
        if multi_probe_bits > 0:
            candidate_hashes |= self._neighboring_hashes(query_hash, multi_probe_bits)

        candidates: dict[str, list[float]] = {}
        for h in candidate_hashes:
            if h in self._buckets:
                candidates.update(self._buckets[h])

        # Score candidates
        scored: list[tuple[str, float]] = []
        for entry_id, entry_vec in candidates.items():
            sim = self._fp.cosine_similarity(vector, entry_vec)
            if sim >= threshold:
                scored.append((entry_id, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def _neighboring_hashes(self, hash_hex: str, max_flip_bits: int) -> set[str]:
        """Generate neighboring bucket hashes by flipping bits in the binary representation."""
        n_bits = self._fp.n_planes
        # hex → int → binary
        hash_int = int(hash_hex, 16)
        neighbors: set[str] = set()

        hex_width = (n_bits + 3) // 4

        for flip_count in range(1, min(max_flip_bits, n_bits) + 1):
            for bits_to_flip in combinations(range(n_bits), flip_count):
                flipped = hash_int
                for bit in bits_to_flip:
                    flipped ^= 1 << bit
                neighbors.add(format(flipped, f"0{hex_width}x"))

        return neighbors

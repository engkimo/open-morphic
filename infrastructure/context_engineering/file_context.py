"""FileContext — Manus Principle 3: filesystem as infinite context.

Instead of keeping everything in the LLM's token window, offload
content to disk and keep only references in context. Content can
always be retrieved when needed — zero information loss.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


class FileContext:
    """Offload large content to filesystem, keep references in context.

    Compression is always lossless: original content is preserved on disk,
    and the reference includes enough info to retrieve it.
    """

    def __init__(self, cache_dir: Path | str = ".morphic/cache") -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def store(self, content: str, label: str = "") -> str:
        """Store content to disk and return a compact reference string.

        The reference can be injected into LLM context instead of the
        full content, saving tokens while preserving retrievability.
        """
        content_hash = self._hash(content)
        file_path = self._cache_dir / f"{content_hash}.txt"
        file_path.write_text(content, encoding="utf-8")

        ref_parts = [f"[Cached: {content_hash}]"]
        if label:
            ref_parts.append(f"[Label: {label}]")
        ref_parts.append(f"[Size: {len(content)} chars]")

        return " ".join(ref_parts)

    def retrieve(self, content_hash: str) -> str | None:
        """Retrieve cached content by hash. Returns None if not found."""
        file_path = self._cache_dir / f"{content_hash}.txt"
        if not file_path.exists():
            return None
        return file_path.read_text(encoding="utf-8")

    def exists(self, content_hash: str) -> bool:
        """Check if content hash exists in cache."""
        return (self._cache_dir / f"{content_hash}.txt").exists()

    @staticmethod
    def _hash(content: str) -> str:
        """SHA-256 hash truncated to 16 hex chars for filenames."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

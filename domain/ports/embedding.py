"""EmbeddingPort — abstraction for text-to-vector embedding backends.

Domain defines WHAT it needs. Infrastructure provides HOW (Ollama, OpenAI, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingPort(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Convert texts to embedding vectors. Returns one vector per input text."""
        ...

    @abstractmethod
    def dimensions(self) -> int:
        """Return the dimensionality of the embedding vectors."""
        ...

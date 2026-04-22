"""Embedding adapters — implementations of EmbeddingPort.

OllamaEmbeddingAdapter: LOCAL_FIRST, $0, uses Ollama /api/embed endpoint.
"""

from __future__ import annotations

import httpx

from domain.ports.embedding import EmbeddingPort


class OllamaEmbeddingAdapter(EmbeddingPort):
    """Ollama-backed embedding via /api/embed HTTP endpoint.

    Uses the batch endpoint: POST /api/embed with {"model": ..., "input": [texts]}.
    Returns one vector per input text.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "all-minilm",
        dimensions: int = 384,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimensions = dimensions
        self._timeout = timeout

    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Call Ollama /api/embed for batch embedding."""
        if not texts:
            return []

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": texts},
            )
            response.raise_for_status()
            data = response.json()
            return data["embeddings"]

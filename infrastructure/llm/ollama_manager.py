"""Ollama lifecycle management — health check, model management, recommendations."""

from __future__ import annotations

import httpx


class OllamaManager:
    """Manages Ollama local LLM server.

    Provides health checks, model listing/pulling, and RAM-based recommendations.
    All HTTP calls go through _request() for testability.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:11434") -> None:
        self._base_url = base_url

    async def _request(
        self, method: str, path: str, *, timeout: float = 5.0, **kwargs: object
    ) -> httpx.Response:
        """HTTP request to Ollama server."""
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout
        ) as client:
            func = getattr(client, method)
            return await func(path, **kwargs)

    async def is_running(self) -> bool:
        """Check if Ollama server is responding."""
        try:
            resp = await self._request("get", "/api/tags")
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def list_models(self) -> list[str]:
        """Return names of installed Ollama models."""
        try:
            resp = await self._request("get", "/api/tags")
            if resp.status_code == 200:
                return [m["name"] for m in resp.json().get("models", [])]
            return []
        except (httpx.ConnectError, httpx.TimeoutException):
            return []

    async def pull_model(self, model: str) -> bool:
        """Pull model from registry. Returns True on success."""
        try:
            resp = await self._request(
                "post",
                "/api/pull",
                json={"name": model, "stream": False},
                timeout=600.0,
            )
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def ensure_model(self, model: str) -> bool:
        """Ensure model is available locally. Pull if missing."""
        models = await self.list_models()
        if model in models:
            return True
        return await self.pull_model(model)

    @staticmethod
    def get_recommended_model(ram_gb: int) -> str:
        """Recommend model based on available RAM.

        8GB  → qwen3:8b
        16GB → qwen3:8b (default)
        32GB → qwen3-coder:30b
        """
        if ram_gb >= 32:
            return "qwen3-coder:30b"
        if ram_gb >= 8:
            return "qwen3:8b"
        return "llama3.2:3b"

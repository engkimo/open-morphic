"""OllamaManagerPort — local LLM lifecycle management.

Domain defines WHAT it needs from a local LLM server. Infrastructure
provides HOW (HTTP to Ollama daemon, mock, etc.).

The port intentionally excludes pure-function helpers (e.g. RAM-based
model recommendation): callers can import those directly from the impl.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class OllamaManagerPort(ABC):
    @abstractmethod
    async def is_running(self) -> bool: ...

    @abstractmethod
    async def list_models(self) -> list[str]: ...

    @abstractmethod
    async def pull_model(self, model: str) -> bool: ...

    @abstractmethod
    async def delete_model(self, model: str) -> bool: ...

    @abstractmethod
    async def model_info(self, model: str) -> dict: ...

    @abstractmethod
    async def get_running_models(self) -> list[dict]: ...

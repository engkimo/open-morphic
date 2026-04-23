"""ManageOllamaUseCase — status, pull, delete, switch, list."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from domain.ports.ollama_manager import OllamaManagerPort

if TYPE_CHECKING:
    from shared.config import Settings


@dataclass
class OllamaStatus:
    """Snapshot of Ollama server state."""

    running: bool
    default_model: str
    models: list[str] = field(default_factory=list)
    running_models: list[dict] = field(default_factory=list)


class ManageOllamaUseCase:
    """Orchestrate Ollama model management operations."""

    def __init__(self, ollama: OllamaManagerPort, settings: Settings) -> None:
        self._ollama = ollama
        self._settings = settings

    async def status(self) -> OllamaStatus:
        """Get full Ollama status."""
        running = await self._ollama.is_running()
        models = await self._ollama.list_models() if running else []
        running_models = await self._ollama.get_running_models() if running else []
        return OllamaStatus(
            running=running,
            default_model=self._settings.ollama_default_model,
            models=models,
            running_models=running_models,
        )

    async def pull(self, model: str) -> bool:
        """Pull a model."""
        return await self._ollama.pull_model(model)

    async def delete(self, model: str) -> bool:
        """Delete a model."""
        return await self._ollama.delete_model(model)

    async def info(self, model: str) -> dict:
        """Get model info."""
        return await self._ollama.model_info(model)

    async def switch_default(self, model: str) -> bool:
        """Switch the default model (ensures it exists first)."""
        available = await self._ollama.list_models()
        if model not in available:
            pulled = await self._ollama.pull_model(model)
            if not pulled:
                return False
        self._settings.ollama_default_model = model
        return True

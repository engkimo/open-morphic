"""In-memory OllamaManagerPort fake for unit tests.

Tracks an internal model registry. `is_running` is settable to simulate
a stopped daemon. All operations are O(n) on the model list — fine for
the small N used in tests.
"""

from __future__ import annotations

from domain.ports.ollama_manager import OllamaManagerPort


class InMemoryOllamaManager(OllamaManagerPort):
    def __init__(
        self,
        *,
        running: bool = True,
        installed: list[str] | None = None,
    ) -> None:
        self.running = running
        self._models: list[str] = list(installed or [])
        self._running_models: list[dict] = []

    async def is_running(self) -> bool:
        return self.running

    async def list_models(self) -> list[str]:
        if not self.running:
            return []
        return list(self._models)

    async def pull_model(self, model: str) -> bool:
        if not self.running:
            return False
        if model not in self._models:
            self._models.append(model)
        return True

    async def delete_model(self, model: str) -> bool:
        if not self.running:
            return False
        if model in self._models:
            self._models.remove(model)
            return True
        return False

    async def model_info(self, model: str) -> dict:
        if not self.running or model not in self._models:
            return {}
        return {"name": model, "size": 0}

    async def get_running_models(self) -> list[dict]:
        if not self.running:
            return []
        return list(self._running_models)

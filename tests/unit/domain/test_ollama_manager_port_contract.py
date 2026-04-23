"""Contract tests for OllamaManagerPort.

Run against the in-memory fake only — the file-backed `OllamaManager`
needs a live HTTP daemon and is exercised separately in
`tests/unit/infrastructure/test_ollama_manager.py`. LSP between the two
is locked via an isinstance assertion in that suite.
"""

from __future__ import annotations

import pytest

from domain.ports.ollama_manager import OllamaManagerPort
from tests.unit.application._fakes.in_memory_ollama_manager import InMemoryOllamaManager


@pytest.fixture
def fake() -> OllamaManagerPort:
    return InMemoryOllamaManager(installed=["qwen3:8b"])


class TestOllamaManagerPortContract:
    async def test_is_running_default_true(self, fake: OllamaManagerPort) -> None:
        assert await fake.is_running() is True

    async def test_list_models_initial(self, fake: OllamaManagerPort) -> None:
        assert await fake.list_models() == ["qwen3:8b"]

    async def test_pull_appends_when_missing(self, fake: OllamaManagerPort) -> None:
        ok = await fake.pull_model("deepseek-r1:8b")
        assert ok is True
        assert "deepseek-r1:8b" in await fake.list_models()

    async def test_pull_idempotent_when_present(self, fake: OllamaManagerPort) -> None:
        before = await fake.list_models()
        await fake.pull_model("qwen3:8b")
        after = await fake.list_models()
        assert before == after

    async def test_delete_removes(self, fake: OllamaManagerPort) -> None:
        ok = await fake.delete_model("qwen3:8b")
        assert ok is True
        assert "qwen3:8b" not in await fake.list_models()

    async def test_delete_missing_returns_false(self, fake: OllamaManagerPort) -> None:
        assert await fake.delete_model("nonexistent") is False

    async def test_model_info_known(self, fake: OllamaManagerPort) -> None:
        info = await fake.model_info("qwen3:8b")
        assert info["name"] == "qwen3:8b"

    async def test_model_info_unknown(self, fake: OllamaManagerPort) -> None:
        assert await fake.model_info("nonexistent") == {}

    async def test_when_not_running_list_empty(self) -> None:
        stopped = InMemoryOllamaManager(running=False, installed=["qwen3:8b"])
        assert await stopped.is_running() is False
        assert await stopped.list_models() == []

    async def test_when_not_running_pull_fails(self) -> None:
        stopped = InMemoryOllamaManager(running=False)
        assert await stopped.pull_model("qwen3:8b") is False

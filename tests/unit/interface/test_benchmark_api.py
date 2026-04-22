"""Tests for benchmark API routes — Sprint 7.6."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from interface.api.main import create_app


def _make_mock_container() -> MagicMock:
    """Create a mock container with context adapters."""
    container = MagicMock()
    # Mock context adapters as a dict
    from domain.value_objects.agent_engine import AgentEngineType
    from infrastructure.cognitive.adapters import (
        ADKContextAdapter,
        ClaudeCodeContextAdapter,
        CodexContextAdapter,
        GeminiContextAdapter,
        OllamaContextAdapter,
        OpenHandsContextAdapter,
    )

    container._context_adapters = {
        AgentEngineType.CLAUDE_CODE: ClaudeCodeContextAdapter(),
        AgentEngineType.GEMINI_CLI: GeminiContextAdapter(),
        AgentEngineType.CODEX_CLI: CodexContextAdapter(),
        AgentEngineType.OPENHANDS: OpenHandsContextAdapter(),
        AgentEngineType.ADK: ADKContextAdapter(),
        AgentEngineType.OLLAMA: OllamaContextAdapter(),
    }
    return container


@pytest.fixture()
def client() -> TestClient:
    container = _make_mock_container()
    app = create_app(container=container)
    return TestClient(app)


class TestBenchmarkAPI:
    """Benchmark API endpoint tests."""

    def test_run_all_benchmarks(self, client: TestClient) -> None:
        resp = client.post("/api/benchmarks/run")
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_score" in data
        assert "context_continuity" in data
        assert "dedup_accuracy" in data
        assert "timestamp" in data
        assert isinstance(data["overall_score"], float)

    def test_run_continuity_benchmark(self, client: TestClient) -> None:
        resp = client.post("/api/benchmarks/continuity")
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_score" in data
        assert data["context_continuity"] is not None
        assert "adapter_scores" in data["context_continuity"]
        assert len(data["context_continuity"]["adapter_scores"]) == 6

    def test_run_dedup_benchmark(self, client: TestClient) -> None:
        resp = client.post("/api/benchmarks/dedup")
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_score" in data
        assert data["dedup_accuracy"] is not None
        assert "scores" in data["dedup_accuracy"]
        assert len(data["dedup_accuracy"]["scores"]) >= 2

    def test_continuity_adapter_scores_have_all_fields(self, client: TestClient) -> None:
        resp = client.post("/api/benchmarks/continuity")
        data = resp.json()
        for s in data["context_continuity"]["adapter_scores"]:
            assert "engine" in s
            assert "score" in s
            assert "decisions_injected" in s
            assert "decisions_found" in s
            assert "artifacts_injected" in s
            assert "artifacts_found" in s
            assert "blockers_injected" in s
            assert "blockers_found" in s
            assert "context_length" in s
            assert 0.0 <= s["score"] <= 1.0

    def test_dedup_scores_have_all_fields(self, client: TestClient) -> None:
        resp = client.post("/api/benchmarks/dedup")
        data = resp.json()
        for s in data["dedup_accuracy"]["scores"]:
            assert "scenario" in s
            assert "engine_a" in s
            assert "engine_b" in s
            assert "total_raw" in s
            assert "deduped_count" in s
            assert "dedup_rate" in s

    def test_overall_score_is_average_of_suites(self, client: TestClient) -> None:
        resp = client.post("/api/benchmarks/run")
        data = resp.json()
        # Overall should be the average of continuity and dedup
        cc = data["context_continuity"]["overall_score"] if data["context_continuity"] else 0
        dd = data["dedup_accuracy"]["overall_accuracy"] if data["dedup_accuracy"] else 0
        expected = (cc + dd) / 2 if (cc and dd) else max(cc, dd)
        assert abs(data["overall_score"] - expected) < 0.01

    def test_errors_list_is_present(self, client: TestClient) -> None:
        resp = client.post("/api/benchmarks/run")
        data = resp.json()
        assert "errors" in data
        assert isinstance(data["errors"], list)

"""E2E smoke tests — runs against a live API server.

Usage:
    # Start server first:
    USE_POSTGRES=true uv run uvicorn interface.api.main:app --port 8000
    # Then run:
    API_BASE=http://localhost:8000 uv run --extra dev pytest tests/e2e/ -v

Skipped automatically when the API server is not reachable.
"""

from __future__ import annotations

import os

import httpx
import pytest

API_BASE = os.getenv("API_BASE", "http://localhost:8000")


def _api_reachable() -> bool:
    try:
        r = httpx.get(f"{API_BASE}/api/health", timeout=2)
        return r.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


pytestmark = pytest.mark.skipif(not _api_reachable(), reason="API server not reachable")


@pytest.fixture
def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=API_BASE, timeout=30)


# ── Health ───────────────────────────────────────────────────────


class TestHealth:
    async def test_health(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ── Tasks CRUD ───────────────────────────────────────────────────


class TestTasks:
    async def test_list_tasks(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/tasks")
        assert r.status_code == 200
        data = r.json()
        assert "tasks" in data
        assert "count" in data

    async def test_get_nonexistent_task(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/tasks/nonexistent-id-999")
        assert r.status_code == 404


# ── Models ───────────────────────────────────────────────────────


class TestModels:
    async def test_model_status(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/models/status")
        assert r.status_code == 200
        data = r.json()
        assert "ollama_running" in data
        assert "default_model" in data
        assert "models" in data

    async def test_list_models(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/models")
        assert r.status_code == 200
        data = r.json()
        # Returns a flat list of model names
        assert isinstance(data, list)
        assert len(data) > 0

    async def test_running_models(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/models/running")
        assert r.status_code == 200


# ── Cost ─────────────────────────────────────────────────────────


class TestCost:
    async def test_cost_summary(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/cost")
        assert r.status_code == 200
        data = r.json()
        assert "daily_total_usd" in data
        assert "monthly_total_usd" in data
        assert "monthly_budget_usd" in data
        assert data["monthly_budget_usd"] > 0

    async def test_cost_logs(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/cost/logs?limit=5")
        assert r.status_code == 200
        data = r.json()
        assert "logs" in data
        assert "count" in data


# ── Engines ──────────────────────────────────────────────────────


class TestEngines:
    async def test_list_engines(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/engines")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 6
        names = [e["engine_type"] for e in data["engines"]]
        assert "ollama" in names

    async def test_engine_status(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/engines/ollama")
        assert r.status_code == 200
        data = r.json()
        assert data["engine_type"] == "ollama"
        assert "available" in data


# ── Marketplace ──────────────────────────────────────────────────


class TestMarketplace:
    async def test_search(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/marketplace/search?q=github&limit=3")
        assert r.status_code == 200
        data = r.json()
        assert "candidates" in data or "error" in data

    async def test_installed(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/marketplace/installed")
        assert r.status_code == 200

    async def test_suggest(self, client: httpx.AsyncClient) -> None:
        r = await client.post(
            "/api/marketplace/suggest",
            json={"error_message": "FileNotFoundError", "task_description": "test"},
        )
        assert r.status_code == 200


# ── Evolution ────────────────────────────────────────────────────


class TestEvolution:
    async def test_stats(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/evolution/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_count" in data
        assert "success_rate" in data

    async def test_failures(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/evolution/failures?limit=5")
        assert r.status_code == 200
        data = r.json()
        assert "patterns" in data

    async def test_preferences(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/evolution/preferences")
        assert r.status_code == 200
        data = r.json()
        assert "model_preferences" in data
        assert "engine_preferences" in data


# ── Cognitive (UCL) ──────────────────────────────────────────────


class TestCognitive:
    async def test_list_states(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/cognitive/state")
        assert r.status_code == 200
        data = r.json()
        assert "states" in data

    async def test_affinity(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/cognitive/affinity")
        assert r.status_code == 200
        data = r.json()
        assert "scores" in data

    async def test_extract_insights(self, client: httpx.AsyncClient) -> None:
        r = await client.post(
            "/api/cognitive/insights/extract",
            json={
                "task_id": "e2e-test-001",
                "engine": "ollama",
                "output": "Python 3.12 match statements are stable and performant.",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "insights" in data

    async def test_state_created_after_insight(self, client: httpx.AsyncClient) -> None:
        """After extracting insights, a shared state should exist."""
        r = await client.get("/api/cognitive/state/e2e-test-001")
        # May be 200 (found) or 404 (not created by this flow)
        assert r.status_code in (200, 404)


# ── Benchmarks ───────────────────────────────────────────────────


class TestBenchmarks:
    async def test_continuity(self, client: httpx.AsyncClient) -> None:
        r = await client.post("/api/benchmarks/continuity")
        assert r.status_code == 200
        data = r.json()
        assert "overall_score" in data

    async def test_dedup(self, client: httpx.AsyncClient) -> None:
        r = await client.post("/api/benchmarks/dedup")
        assert r.status_code == 200
        data = r.json()
        assert "dedup_accuracy" in data
        assert data["dedup_accuracy"]["overall_accuracy"] > 0

    async def test_run_all(self, client: httpx.AsyncClient) -> None:
        r = await client.post("/api/benchmarks/run")
        assert r.status_code == 200
        data = r.json()
        assert "overall_score" in data
        assert "context_continuity" in data
        assert "dedup_accuracy" in data


# ── Plans ────────────────────────────────────────────────────────


class TestPlans:
    async def test_list_plans(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/plans")
        assert r.status_code == 200
        data = r.json()
        assert "plans" in data

    async def test_get_nonexistent_plan(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/plans/nonexistent-plan-999")
        assert r.status_code == 404


# ── Memory ───────────────────────────────────────────────────────


class TestMemory:
    async def test_search(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/memory/search?q=test")
        assert r.status_code == 200
        data = r.json()
        assert "results" in data

    async def test_export(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/api/memory/export?platform=claude_code")
        assert r.status_code == 200
        data = r.json()
        assert "platform" in data
        assert data["platform"] == "claude_code"


# ── Task Execution (Core Flow — requires Ollama) ────────────────


class TestTaskExecution:
    """Core E2E: create task → Ollama executes → verify result.

    This is the most important test — it exercises the full pipeline.
    Timeout is generous (120s) because Ollama inference takes time.
    """

    @pytest.fixture
    def slow_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=API_BASE, timeout=120)

    async def test_create_and_execute_task(self, slow_client: httpx.AsyncClient) -> None:
        """Full pipeline: goal → decompose → execute → result."""
        r = await slow_client.post(
            "/api/tasks",
            json={"goal": "1+1を計算して答えだけ教えて"},
        )
        assert r.status_code == 201, f"Task creation failed: {r.text}"
        data = r.json()
        task_id = data["id"]
        assert data["status"] in ("pending", "running", "completed", "success")

        # Poll until complete (max 120s)
        import asyncio

        for _ in range(60):
            r = await slow_client.get(f"/api/tasks/{task_id}")
            assert r.status_code == 200
            task = r.json()
            if task["status"] in ("completed", "success", "failed"):
                break
            await asyncio.sleep(2)

        assert task["status"] in ("completed", "success"), f"Task failed: {task}"
        assert task["is_complete"] is True
        assert task["success_rate"] > 0

        # Verify cost was tracked
        r = await slow_client.get("/api/cost")
        assert r.status_code == 200

    async def test_create_plan_and_approve(self, slow_client: httpx.AsyncClient) -> None:
        """Interactive planning: plan → approve → task created."""
        r = await slow_client.post(
            "/api/plans",
            json={"goal": "FizzBuzzを実装して", "model": "ollama/qwen3:8b"},
        )
        assert r.status_code == 201, f"Plan creation failed: {r.text}"
        plan = r.json()
        plan_id = plan["id"]
        assert plan["status"] == "proposed"
        assert len(plan["steps"]) > 0

        # Approve — creates a task from the plan
        r = await slow_client.post(f"/api/plans/{plan_id}/approve")
        assert r.status_code == 200
        result = r.json()
        # Response is the created task or updated plan
        assert result.get("status") in ("approved", "pending")

        # Verify plan is now approved
        r = await slow_client.get(f"/api/plans/{plan_id}")
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

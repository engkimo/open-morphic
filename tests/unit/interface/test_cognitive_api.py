"""Tests for cognitive / UCL API routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from domain.entities.cognitive import (
    AgentAction,
    AgentAffinityScore,
    Decision,
    SharedTaskState,
)
from domain.value_objects.agent_engine import AgentEngineType


def _make_app():  # type: ignore[no-untyped-def]
    """Create a test app with minimal UCL container."""
    from infrastructure.cognitive.affinity_store import InMemoryAgentAffinityRepository
    from infrastructure.persistence.in_memory import InMemoryMemoryRepository
    from infrastructure.persistence.shared_task_state_repo import (
        InMemorySharedTaskStateRepository,
    )
    from interface.api.main import create_app

    class TestContainer:
        def __init__(self) -> None:
            self.shared_task_state_repo = InMemorySharedTaskStateRepository()
            self.affinity_repo = InMemoryAgentAffinityRepository()
            self.memory_repo = InMemoryMemoryRepository()
            # extract_insights and handoff_task need more wiring;
            # we test those endpoints for validation only
            self.extract_insights = _FakeExtractInsights()
            self.handoff_task = _FakeHandoffTask()

    container = TestContainer()
    app = create_app(container=container)
    return app, container


class _FakeExtractInsights:
    async def extract_and_store(self, *, task_id: str, engine: AgentEngineType, output: str):  # type: ignore[no-untyped-def]
        from domain.ports.insight_extractor import ExtractedInsight
        from domain.value_objects.cognitive import CognitiveMemoryType

        return [
            ExtractedInsight(
                content=f"insight from {output[:20]}",
                memory_type=CognitiveMemoryType.SEMANTIC,
                confidence=0.8,
                source_engine=engine,
                tags=["test"],
            )
        ]


class _FakeHandoffTask:
    async def handoff(self, request):  # type: ignore[no-untyped-def]
        from application.use_cases.handoff_task import HandoffResult

        return HandoffResult(
            success=True,
            source_engine=request.source_engine,
            target_engine=request.target_engine or AgentEngineType.OLLAMA,
        )


def _make_state(task_id: str = "task-1") -> SharedTaskState:
    state = SharedTaskState(task_id=task_id)
    state.add_decision(
        Decision(
            description="Use Ollama for cost",
            rationale="Budget is $0",
            agent_engine=AgentEngineType.OLLAMA,
            confidence=0.9,
        )
    )
    state.add_action(
        AgentAction(
            agent_engine=AgentEngineType.OLLAMA,
            action_type="execute",
            summary="Ran fibonacci task",
            cost_usd=0.0,
        )
    )
    state.add_artifact("code", "def fib(n): ...")
    return state


class TestCognitiveStateAPI:
    def setup_method(self) -> None:
        self.app, self.container = _make_app()
        self.client = TestClient(self.app)

    def test_list_states_empty(self) -> None:
        resp = self.client.get("/api/cognitive/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["states"] == []

    @pytest.mark.asyncio
    async def test_list_states_with_data(self) -> None:
        state = _make_state()
        await self.container.shared_task_state_repo.save(state)
        resp = self.client.get("/api/cognitive/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["states"][0]["task_id"] == "task-1"

    @pytest.mark.asyncio
    async def test_get_state(self) -> None:
        state = _make_state("task-42")
        await self.container.shared_task_state_repo.save(state)
        resp = self.client.get("/api/cognitive/state/task-42")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "task-42"
        assert len(data["decisions"]) == 1
        assert data["decisions"][0]["description"] == "Use Ollama for cost"
        assert len(data["agent_history"]) == 1
        assert data["artifacts"]["code"] == "def fib(n): ..."
        assert data["last_agent"] == "ollama"
        assert data["total_cost_usd"] == 0.0

    def test_get_state_not_found(self) -> None:
        resp = self.client.get("/api/cognitive/state/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_state(self) -> None:
        state = _make_state("task-del")
        await self.container.shared_task_state_repo.save(state)
        resp = self.client.delete("/api/cognitive/state/task-del")
        assert resp.status_code == 204
        # Verify deleted
        resp2 = self.client.get("/api/cognitive/state/task-del")
        assert resp2.status_code == 404

    def test_delete_state_not_found(self) -> None:
        resp = self.client.delete("/api/cognitive/state/nonexistent")
        assert resp.status_code == 404


class TestCognitiveAffinityAPI:
    def setup_method(self) -> None:
        self.app, self.container = _make_app()
        self.client = TestClient(self.app)

    def test_list_affinities_empty(self) -> None:
        resp = self.client.get("/api/cognitive/affinity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_list_affinities_with_data(self) -> None:
        score = AgentAffinityScore(
            engine=AgentEngineType.CLAUDE_CODE,
            topic="backend",
            familiarity=0.8,
            recency=0.9,
            success_rate=0.95,
            cost_efficiency=0.3,
            sample_count=10,
        )
        await self.container.affinity_repo.upsert(score)
        resp = self.client.get("/api/cognitive/affinity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["scores"][0]["engine"] == "claude_code"
        assert data["scores"][0]["topic"] == "backend"
        assert data["scores"][0]["score"] > 0

    @pytest.mark.asyncio
    async def test_filter_by_topic(self) -> None:
        for engine in [AgentEngineType.OLLAMA, AgentEngineType.CLAUDE_CODE]:
            await self.container.affinity_repo.upsert(
                AgentAffinityScore(
                    engine=engine,
                    topic="frontend",
                    familiarity=0.5,
                    success_rate=0.8,
                    sample_count=5,
                )
            )
        await self.container.affinity_repo.upsert(
            AgentAffinityScore(
                engine=AgentEngineType.OLLAMA,
                topic="backend",
                familiarity=0.3,
                sample_count=2,
            )
        )
        resp = self.client.get("/api/cognitive/affinity?topic=frontend")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert all(s["topic"] == "frontend" for s in data["scores"])

    @pytest.mark.asyncio
    async def test_filter_by_engine(self) -> None:
        await self.container.affinity_repo.upsert(
            AgentAffinityScore(
                engine=AgentEngineType.OLLAMA,
                topic="testing",
                familiarity=0.6,
                sample_count=3,
            )
        )
        resp = self.client.get("/api/cognitive/affinity?engine=ollama")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1

    def test_filter_by_invalid_engine(self) -> None:
        resp = self.client.get("/api/cognitive/affinity?engine=invalid")
        assert resp.status_code == 400


class TestCognitiveHandoffAPI:
    def setup_method(self) -> None:
        self.app, self.container = _make_app()
        self.client = TestClient(self.app)

    def test_handoff_success(self) -> None:
        resp = self.client.post(
            "/api/cognitive/handoff",
            json={
                "task": "Fix auth bug",
                "task_id": "t-1",
                "source_engine": "ollama",
                "reason": "Need complex reasoning",
                "target_engine": "claude_code",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["source_engine"] == "ollama"
        assert data["target_engine"] == "claude_code"

    def test_handoff_invalid_source(self) -> None:
        resp = self.client.post(
            "/api/cognitive/handoff",
            json={
                "task": "test",
                "task_id": "t-1",
                "source_engine": "invalid",
                "reason": "test",
            },
        )
        assert resp.status_code == 400

    def test_handoff_invalid_target(self) -> None:
        resp = self.client.post(
            "/api/cognitive/handoff",
            json={
                "task": "test",
                "task_id": "t-1",
                "source_engine": "ollama",
                "reason": "test",
                "target_engine": "invalid",
            },
        )
        assert resp.status_code == 400

    def test_handoff_invalid_task_type(self) -> None:
        resp = self.client.post(
            "/api/cognitive/handoff",
            json={
                "task": "test",
                "task_id": "t-1",
                "source_engine": "ollama",
                "reason": "test",
                "task_type": "invalid_type",
            },
        )
        assert resp.status_code == 400

    def test_handoff_missing_required_fields(self) -> None:
        resp = self.client.post("/api/cognitive/handoff", json={})
        assert resp.status_code == 422


class TestCognitiveInsightsAPI:
    def setup_method(self) -> None:
        self.app, self.container = _make_app()
        self.client = TestClient(self.app)

    def test_extract_insights(self) -> None:
        resp = self.client.post(
            "/api/cognitive/insights/extract",
            json={
                "task_id": "t-1",
                "engine": "ollama",
                "output": "The database needs indexing for performance",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert "insight" in data["insights"][0]["content"]

    def test_extract_invalid_engine(self) -> None:
        resp = self.client.post(
            "/api/cognitive/insights/extract",
            json={
                "task_id": "t-1",
                "engine": "invalid",
                "output": "some output",
            },
        )
        assert resp.status_code == 400

    def test_extract_missing_fields(self) -> None:
        resp = self.client.post(
            "/api/cognitive/insights/extract",
            json={"task_id": "t-1"},
        )
        assert resp.status_code == 422


class TestCognitiveConflictsAPI:
    def setup_method(self) -> None:
        self.app, self.container = _make_app()
        self.client = TestClient(self.app)

    def test_conflicts_empty(self) -> None:
        resp = self.client.post(
            "/api/cognitive/conflicts",
            json={"limit": 100},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["conflicts"] == []
        assert data["insights_analyzed"] == 0

    @pytest.mark.asyncio
    async def test_conflicts_detected(self) -> None:
        from domain.entities.memory import MemoryEntry
        from domain.value_objects.status import MemoryType

        m1 = MemoryEntry(
            content="uses PostgreSQL for persistence",
            memory_type=MemoryType.L2_SEMANTIC,
            importance_score=0.9,
            metadata={"source_engine": "claude_code"},
        )
        m2 = MemoryEntry(
            content="not uses PostgreSQL for persistence",
            memory_type=MemoryType.L2_SEMANTIC,
            importance_score=0.5,
            metadata={"source_engine": "gemini_cli"},
        )
        await self.container.memory_repo.add(m1)
        await self.container.memory_repo.add(m2)

        resp = self.client.post(
            "/api/cognitive/conflicts",
            json={"limit": 100},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        assert data["insights_analyzed"] >= 2
        conflict = data["conflicts"][0]
        assert "overlap_score" in conflict
        assert conflict["winner"] in ("a", "b")

    @pytest.mark.asyncio
    async def test_conflicts_resolve(self) -> None:
        from domain.entities.memory import MemoryEntry
        from domain.value_objects.status import MemoryType

        m1 = MemoryEntry(
            content="deploy to production with Docker",
            memory_type=MemoryType.L3_FACTS,
            importance_score=0.9,
            metadata={"source_engine": "claude_code"},
        )
        m2 = MemoryEntry(
            content="never deploy to production with Docker",
            memory_type=MemoryType.L3_FACTS,
            importance_score=0.4,
            metadata={"source_engine": "ollama"},
        )
        await self.container.memory_repo.add(m1)
        await self.container.memory_repo.add(m2)

        resp = self.client.post(
            "/api/cognitive/conflicts",
            json={"limit": 100, "resolve": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        assert data["survivors"] is not None
        # Winner should be "a" (higher confidence)
        assert data["conflicts"][0]["winner"] == "a"

    @pytest.mark.asyncio
    async def test_conflicts_no_conflict_same_engine(self) -> None:
        from domain.entities.memory import MemoryEntry
        from domain.value_objects.status import MemoryType

        m1 = MemoryEntry(
            content="uses PostgreSQL for persistence",
            memory_type=MemoryType.L2_SEMANTIC,
            importance_score=0.9,
            metadata={"source_engine": "ollama"},
        )
        m2 = MemoryEntry(
            content="not uses PostgreSQL for persistence",
            memory_type=MemoryType.L2_SEMANTIC,
            importance_score=0.5,
            metadata={"source_engine": "ollama"},
        )
        await self.container.memory_repo.add(m1)
        await self.container.memory_repo.add(m2)

        resp = self.client.post(
            "/api/cognitive/conflicts",
            json={"limit": 100},
        )
        assert resp.status_code == 200
        # Same engine → no conflict
        assert resp.json()["count"] == 0

    def test_conflicts_default_body(self) -> None:
        resp = self.client.post(
            "/api/cognitive/conflicts",
            json={},
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

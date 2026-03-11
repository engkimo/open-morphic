"""Tests for affinity stores — InMemory and JSONL implementations.

Sprint 7.4: Affinity-Aware Routing + Task Handoff
"""

from __future__ import annotations

from pathlib import Path

from domain.entities.cognitive import AgentAffinityScore
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.cognitive.affinity_store import (
    InMemoryAgentAffinityRepository,
    JSONLAffinityStore,
)


def _make_score(
    engine: AgentEngineType = AgentEngineType.CLAUDE_CODE,
    topic: str = "frontend",
    familiarity: float = 0.8,
    sample_count: int = 5,
) -> AgentAffinityScore:
    return AgentAffinityScore(
        engine=engine,
        topic=topic,
        familiarity=familiarity,
        recency=0.7,
        success_rate=0.9,
        cost_efficiency=0.6,
        sample_count=sample_count,
    )


# ═══════════════════════════════════════════════════════════════
# InMemoryAgentAffinityRepository
# ═══════════════════════════════════════════════════════════════


class TestInMemoryAffinityGet:
    async def test_get_returns_none_when_empty(self) -> None:
        repo = InMemoryAgentAffinityRepository()
        result = await repo.get(AgentEngineType.CLAUDE_CODE, "frontend")
        assert result is None

    async def test_get_returns_stored_score(self) -> None:
        repo = InMemoryAgentAffinityRepository()
        score = _make_score()
        await repo.upsert(score)
        result = await repo.get(AgentEngineType.CLAUDE_CODE, "frontend")
        assert result is not None
        assert result.familiarity == 0.8


class TestInMemoryAffinityByTopic:
    async def test_get_by_topic_returns_all_engines(self) -> None:
        repo = InMemoryAgentAffinityRepository()
        await repo.upsert(_make_score(AgentEngineType.CLAUDE_CODE, "frontend"))
        await repo.upsert(_make_score(AgentEngineType.GEMINI_CLI, "frontend"))
        await repo.upsert(_make_score(AgentEngineType.OLLAMA, "backend"))
        result = await repo.get_by_topic("frontend")
        assert len(result) == 2

    async def test_get_by_topic_empty(self) -> None:
        repo = InMemoryAgentAffinityRepository()
        result = await repo.get_by_topic("unknown")
        assert result == []


class TestInMemoryAffinityByEngine:
    async def test_get_by_engine_returns_all_topics(self) -> None:
        repo = InMemoryAgentAffinityRepository()
        await repo.upsert(_make_score(AgentEngineType.CLAUDE_CODE, "frontend"))
        await repo.upsert(_make_score(AgentEngineType.CLAUDE_CODE, "backend"))
        await repo.upsert(_make_score(AgentEngineType.OLLAMA, "frontend"))
        result = await repo.get_by_engine(AgentEngineType.CLAUDE_CODE)
        assert len(result) == 2


class TestInMemoryAffinityUpsert:
    async def test_upsert_creates_new(self) -> None:
        repo = InMemoryAgentAffinityRepository()
        await repo.upsert(_make_score())
        assert len(await repo.list_all()) == 1

    async def test_upsert_overwrites_existing(self) -> None:
        repo = InMemoryAgentAffinityRepository()
        await repo.upsert(_make_score(familiarity=0.5))
        await repo.upsert(_make_score(familiarity=0.9))
        result = await repo.get(AgentEngineType.CLAUDE_CODE, "frontend")
        assert result is not None
        assert result.familiarity == 0.9
        assert len(await repo.list_all()) == 1


class TestInMemoryAffinityListAll:
    async def test_list_all_empty(self) -> None:
        repo = InMemoryAgentAffinityRepository()
        assert await repo.list_all() == []

    async def test_list_all_multiple(self) -> None:
        repo = InMemoryAgentAffinityRepository()
        await repo.upsert(_make_score(AgentEngineType.CLAUDE_CODE, "frontend"))
        await repo.upsert(_make_score(AgentEngineType.GEMINI_CLI, "backend"))
        result = await repo.list_all()
        assert len(result) == 2


# ═══════════════════════════════════════════════════════════════
# JSONLAffinityStore
# ═══════════════════════════════════════════════════════════════


class TestJSONLAffinityStore:
    async def test_upsert_and_get(self, tmp_path: Path) -> None:
        store = JSONLAffinityStore(tmp_path)
        score = _make_score()
        await store.upsert(score)
        result = await store.get(AgentEngineType.CLAUDE_CODE, "frontend")
        assert result is not None
        assert result.familiarity == 0.8

    async def test_persists_to_disk(self, tmp_path: Path) -> None:
        store = JSONLAffinityStore(tmp_path)
        await store.upsert(_make_score())
        # Create new store instance — should load from disk
        store2 = JSONLAffinityStore(tmp_path)
        result = await store2.get(AgentEngineType.CLAUDE_CODE, "frontend")
        assert result is not None
        assert result.familiarity == 0.8

    async def test_upsert_overwrites(self, tmp_path: Path) -> None:
        store = JSONLAffinityStore(tmp_path)
        await store.upsert(_make_score(familiarity=0.5))
        await store.upsert(_make_score(familiarity=0.9))
        result = await store.get(AgentEngineType.CLAUDE_CODE, "frontend")
        assert result is not None
        assert result.familiarity == 0.9

    async def test_get_by_topic(self, tmp_path: Path) -> None:
        store = JSONLAffinityStore(tmp_path)
        await store.upsert(_make_score(AgentEngineType.CLAUDE_CODE, "frontend"))
        await store.upsert(_make_score(AgentEngineType.GEMINI_CLI, "frontend"))
        result = await store.get_by_topic("frontend")
        assert len(result) == 2

    async def test_get_by_engine(self, tmp_path: Path) -> None:
        store = JSONLAffinityStore(tmp_path)
        await store.upsert(_make_score(AgentEngineType.CLAUDE_CODE, "frontend"))
        await store.upsert(_make_score(AgentEngineType.CLAUDE_CODE, "backend"))
        result = await store.get_by_engine(AgentEngineType.CLAUDE_CODE)
        assert len(result) == 2

    async def test_list_all(self, tmp_path: Path) -> None:
        store = JSONLAffinityStore(tmp_path)
        await store.upsert(_make_score(AgentEngineType.CLAUDE_CODE, "frontend"))
        await store.upsert(_make_score(AgentEngineType.GEMINI_CLI, "backend"))
        result = await store.list_all()
        assert len(result) == 2

    async def test_empty_dir_returns_none(self, tmp_path: Path) -> None:
        store = JSONLAffinityStore(tmp_path)
        result = await store.get(AgentEngineType.CLAUDE_CODE, "frontend")
        assert result is None

    async def test_creates_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / "sub" / "dir"
        store = JSONLAffinityStore(nested)
        await store.upsert(_make_score())
        assert nested.exists()

    async def test_skips_invalid_lines(self, tmp_path: Path) -> None:
        """Invalid JSONL lines are skipped gracefully."""
        path = tmp_path / "affinity_scores.jsonl"
        path.write_text("not valid json\n")
        store = JSONLAffinityStore(tmp_path)
        result = await store.list_all()
        assert result == []

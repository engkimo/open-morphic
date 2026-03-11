"""Affinity stores — InMemory and JSONL persistence for AgentAffinityScore.

Two implementations of AgentAffinityRepository:
- InMemoryAgentAffinityRepository: dict keyed by (engine, topic) tuple
- JSONLAffinityStore: JSONL file persistence following StrategyStore pattern
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from domain.entities.cognitive import AgentAffinityScore
from domain.ports.agent_affinity_repository import AgentAffinityRepository
from domain.value_objects.agent_engine import AgentEngineType

logger = logging.getLogger(__name__)


class InMemoryAgentAffinityRepository(AgentAffinityRepository):
    """In-memory implementation keyed by (engine, topic) tuple."""

    def __init__(self) -> None:
        self._store: dict[tuple[AgentEngineType, str], AgentAffinityScore] = {}

    async def get(self, engine: AgentEngineType, topic: str) -> AgentAffinityScore | None:
        return self._store.get((engine, topic))

    async def get_by_topic(self, topic: str) -> list[AgentAffinityScore]:
        return [s for (e, t), s in self._store.items() if t == topic]

    async def get_by_engine(self, engine: AgentEngineType) -> list[AgentAffinityScore]:
        return [s for (e, t), s in self._store.items() if e == engine]

    async def upsert(self, score: AgentAffinityScore) -> None:
        self._store[(score.engine, score.topic)] = score

    async def list_all(self) -> list[AgentAffinityScore]:
        return list(self._store.values())


class JSONLAffinityStore(AgentAffinityRepository):
    """JSONL file-based persistence for affinity scores.

    Follows the StrategyStore pattern: full-overwrite on save, line-by-line parsing on load.
    File: {base_dir}/affinity_scores.jsonl
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[tuple[AgentEngineType, str], AgentAffinityScore] = {}
        self._loaded = False

    @property
    def _path(self) -> Path:
        return self._base_dir / "affinity_scores.jsonl"

    def _ensure_loaded(self) -> None:
        """Lazy-load from disk on first access."""
        if self._loaded:
            return
        self._cache.clear()
        if self._path.exists():
            for line in self._path.read_text(encoding="utf-8").strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    score = AgentAffinityScore.model_validate(data, strict=False)
                    self._cache[(score.engine, score.topic)] = score
                except (json.JSONDecodeError, Exception) as exc:
                    logger.warning("Skipping invalid JSONL line in %s: %s", self._path, exc)
        self._loaded = True

    def _flush(self) -> None:
        """Write all cached scores to disk (full overwrite)."""
        with open(self._path, "w", encoding="utf-8") as f:
            for score in self._cache.values():
                f.write(json.dumps(score.model_dump(mode="json"), ensure_ascii=False) + "\n")

    async def get(self, engine: AgentEngineType, topic: str) -> AgentAffinityScore | None:
        self._ensure_loaded()
        return self._cache.get((engine, topic))

    async def get_by_topic(self, topic: str) -> list[AgentAffinityScore]:
        self._ensure_loaded()
        return [s for (e, t), s in self._cache.items() if t == topic]

    async def get_by_engine(self, engine: AgentEngineType) -> list[AgentAffinityScore]:
        self._ensure_loaded()
        return [s for (e, t), s in self._cache.items() if e == engine]

    async def upsert(self, score: AgentAffinityScore) -> None:
        self._ensure_loaded()
        self._cache[(score.engine, score.topic)] = score
        self._flush()

    async def list_all(self) -> list[AgentAffinityScore]:
        self._ensure_loaded()
        return list(self._cache.values())

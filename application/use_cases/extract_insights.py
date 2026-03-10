"""Extract insights use case — orchestrates the full extraction pipeline.

Flow: extract → conflict resolve → store memories → update task state.
"""

from __future__ import annotations

import logging

from domain.entities.cognitive import Decision, SharedTaskState
from domain.entities.memory import MemoryEntry
from domain.ports.insight_extractor import ExtractedInsight, InsightExtractorPort
from domain.ports.memory_repository import MemoryRepository
from domain.ports.shared_task_state_repository import SharedTaskStateRepository
from domain.services.conflict_resolver import ConflictResolver
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.cognitive import CognitiveMemoryType
from domain.value_objects.status import MemoryType

logger = logging.getLogger(__name__)

# CognitiveMemoryType → MemoryType mapping
_MEMORY_TYPE_MAP: dict[CognitiveMemoryType, MemoryType] = {
    CognitiveMemoryType.EPISODIC: MemoryType.L2_SEMANTIC,
    CognitiveMemoryType.PROCEDURAL: MemoryType.L2_SEMANTIC,
    CognitiveMemoryType.SEMANTIC: MemoryType.L3_FACTS,
    CognitiveMemoryType.WORKING: MemoryType.L1_ACTIVE,
}


class ExtractInsightsUseCase:
    """Orchestrate insight extraction, conflict resolution, and storage."""

    def __init__(
        self,
        extractor: InsightExtractorPort,
        memory_repo: MemoryRepository,
        task_state_repo: SharedTaskStateRepository,
    ) -> None:
        self._extractor = extractor
        self._memory_repo = memory_repo
        self._task_state_repo = task_state_repo

    async def extract_and_store(
        self,
        task_id: str,
        engine: AgentEngineType,
        output: str,
    ) -> list[ExtractedInsight]:
        """Run the full pipeline: extract → resolve → store → update state."""
        # 1. Extract
        insights = await self._extractor.extract_from_output(engine, output)
        if not insights:
            return []

        # 2. Conflict resolve
        survivors, conflicts = ConflictResolver.resolve_all(insights)
        for cp in conflicts:
            logger.info(
                "Conflict resolved: '%s' vs '%s' → winner='%s'",
                cp.insight_a.content[:60],
                cp.insight_b.content[:60],
                cp.resolved_winner.content[:60],
            )

        # 3. Store as MemoryEntry
        for insight in survivors:
            entry = MemoryEntry(
                content=insight.content,
                memory_type=_MEMORY_TYPE_MAP.get(insight.memory_type, MemoryType.L2_SEMANTIC),
                importance_score=insight.confidence,
                metadata={
                    "source_engine": insight.source_engine.value,
                    "cognitive_type": insight.memory_type.value,
                    "tags": insight.tags,
                    "task_id": task_id,
                },
            )
            await self._memory_repo.add(entry)

        # 4. Update SharedTaskState
        await self._update_task_state(task_id, engine, survivors)

        return survivors

    async def _update_task_state(
        self,
        task_id: str,
        engine: AgentEngineType,
        insights: list[ExtractedInsight],
    ) -> None:
        state = await self._task_state_repo.get(task_id)
        if state is None:
            state = SharedTaskState(task_id=task_id)

        for insight in insights:
            if "decision" in insight.tags:
                state.add_decision(
                    Decision(
                        description=insight.content,
                        rationale=f"Extracted from {engine.value} output",
                        agent_engine=engine,
                        confidence=insight.confidence,
                    )
                )
            if any(t in insight.tags for t in ("artifact", "file")):
                state.add_artifact(
                    key=insight.content[:80],
                    value=insight.content,
                )

        await self._task_state_repo.save(state)

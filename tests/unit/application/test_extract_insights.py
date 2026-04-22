"""Tests for ExtractInsightsUseCase."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from application.use_cases.extract_insights import ExtractInsightsUseCase
from domain.entities.cognitive import SharedTaskState
from domain.ports.insight_extractor import ExtractedInsight, InsightExtractorPort
from domain.ports.memory_repository import MemoryRepository
from domain.ports.shared_task_state_repository import SharedTaskStateRepository
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.cognitive import CognitiveMemoryType
from domain.value_objects.status import MemoryType


def _insight(
    content: str = "some fact",
    mem_type: CognitiveMemoryType = CognitiveMemoryType.SEMANTIC,
    confidence: float = 0.7,
    engine: AgentEngineType = AgentEngineType.CLAUDE_CODE,
    tags: list[str] | None = None,
) -> ExtractedInsight:
    return ExtractedInsight(
        content=content,
        memory_type=mem_type,
        confidence=confidence,
        source_engine=engine,
        tags=tags or [],
    )


@pytest.fixture
def extractor_mock() -> InsightExtractorPort:
    mock = AsyncMock(spec=InsightExtractorPort)
    mock.extract_from_output.return_value = [_insight()]
    return mock


@pytest.fixture
def memory_repo() -> MemoryRepository:
    mock = AsyncMock(spec=MemoryRepository)
    return mock


@pytest.fixture
def task_state_repo() -> SharedTaskStateRepository:
    mock = AsyncMock(spec=SharedTaskStateRepository)
    mock.get.return_value = None
    return mock


@pytest.fixture
def use_case(
    extractor_mock: InsightExtractorPort,
    memory_repo: MemoryRepository,
    task_state_repo: SharedTaskStateRepository,
) -> ExtractInsightsUseCase:
    return ExtractInsightsUseCase(
        extractor=extractor_mock,
        memory_repo=memory_repo,
        task_state_repo=task_state_repo,
    )


class TestExtractAndStore:
    """ExtractInsightsUseCase.extract_and_store."""

    @pytest.mark.anyio
    async def test_returns_extracted_insights(self, use_case: ExtractInsightsUseCase) -> None:
        result = await use_case.extract_and_store("task-1", AgentEngineType.CLAUDE_CODE, "output")
        assert len(result) == 1
        assert result[0].content == "some fact"

    @pytest.mark.anyio
    async def test_empty_extraction_returns_empty(
        self,
        extractor_mock: InsightExtractorPort,
        memory_repo: MemoryRepository,
        task_state_repo: SharedTaskStateRepository,
    ) -> None:
        extractor_mock.extract_from_output.return_value = []
        uc = ExtractInsightsUseCase(extractor_mock, memory_repo, task_state_repo)
        result = await uc.extract_and_store("task-1", AgentEngineType.CLAUDE_CODE, "output")
        assert result == []
        memory_repo.add.assert_not_called()

    @pytest.mark.anyio
    async def test_stores_memory_entries(
        self,
        use_case: ExtractInsightsUseCase,
        memory_repo: MemoryRepository,
    ) -> None:
        await use_case.extract_and_store("task-1", AgentEngineType.CLAUDE_CODE, "output")
        memory_repo.add.assert_called_once()
        entry = memory_repo.add.call_args[0][0]
        assert entry.content == "some fact"
        assert entry.importance_score == 0.7

    @pytest.mark.anyio
    async def test_semantic_maps_to_l3_facts(
        self,
        use_case: ExtractInsightsUseCase,
        memory_repo: MemoryRepository,
    ) -> None:
        await use_case.extract_and_store("task-1", AgentEngineType.CLAUDE_CODE, "output")
        entry = memory_repo.add.call_args[0][0]
        assert entry.memory_type == MemoryType.L3_FACTS

    @pytest.mark.anyio
    async def test_episodic_maps_to_l2_semantic(
        self,
        extractor_mock: InsightExtractorPort,
        memory_repo: MemoryRepository,
        task_state_repo: SharedTaskStateRepository,
    ) -> None:
        extractor_mock.extract_from_output.return_value = [
            _insight(mem_type=CognitiveMemoryType.EPISODIC)
        ]
        uc = ExtractInsightsUseCase(extractor_mock, memory_repo, task_state_repo)
        await uc.extract_and_store("t", AgentEngineType.CLAUDE_CODE, "o")
        entry = memory_repo.add.call_args[0][0]
        assert entry.memory_type == MemoryType.L2_SEMANTIC

    @pytest.mark.anyio
    async def test_working_maps_to_l1_active(
        self,
        extractor_mock: InsightExtractorPort,
        memory_repo: MemoryRepository,
        task_state_repo: SharedTaskStateRepository,
    ) -> None:
        extractor_mock.extract_from_output.return_value = [
            _insight(mem_type=CognitiveMemoryType.WORKING)
        ]
        uc = ExtractInsightsUseCase(extractor_mock, memory_repo, task_state_repo)
        await uc.extract_and_store("t", AgentEngineType.CLAUDE_CODE, "o")
        entry = memory_repo.add.call_args[0][0]
        assert entry.memory_type == MemoryType.L1_ACTIVE

    @pytest.mark.anyio
    async def test_procedural_maps_to_l2_semantic(
        self,
        extractor_mock: InsightExtractorPort,
        memory_repo: MemoryRepository,
        task_state_repo: SharedTaskStateRepository,
    ) -> None:
        extractor_mock.extract_from_output.return_value = [
            _insight(mem_type=CognitiveMemoryType.PROCEDURAL)
        ]
        uc = ExtractInsightsUseCase(extractor_mock, memory_repo, task_state_repo)
        await uc.extract_and_store("t", AgentEngineType.CLAUDE_CODE, "o")
        entry = memory_repo.add.call_args[0][0]
        assert entry.memory_type == MemoryType.L2_SEMANTIC

    @pytest.mark.anyio
    async def test_metadata_includes_source_engine(
        self,
        use_case: ExtractInsightsUseCase,
        memory_repo: MemoryRepository,
    ) -> None:
        await use_case.extract_and_store("task-1", AgentEngineType.CLAUDE_CODE, "output")
        entry = memory_repo.add.call_args[0][0]
        assert entry.metadata["source_engine"] == "claude_code"
        assert entry.metadata["task_id"] == "task-1"

    @pytest.mark.anyio
    async def test_creates_task_state_if_not_exists(
        self,
        use_case: ExtractInsightsUseCase,
        task_state_repo: SharedTaskStateRepository,
    ) -> None:
        task_state_repo.get.return_value = None
        await use_case.extract_and_store("task-1", AgentEngineType.CLAUDE_CODE, "output")
        task_state_repo.save.assert_called_once()
        saved = task_state_repo.save.call_args[0][0]
        assert saved.task_id == "task-1"

    @pytest.mark.anyio
    async def test_reuses_existing_task_state(
        self,
        use_case: ExtractInsightsUseCase,
        task_state_repo: SharedTaskStateRepository,
    ) -> None:
        existing = SharedTaskState(task_id="task-1")
        task_state_repo.get.return_value = existing
        await use_case.extract_and_store("task-1", AgentEngineType.CLAUDE_CODE, "output")
        task_state_repo.save.assert_called_once()
        saved = task_state_repo.save.call_args[0][0]
        assert saved is existing

    @pytest.mark.anyio
    async def test_decision_tagged_insight_adds_decision(
        self,
        extractor_mock: InsightExtractorPort,
        memory_repo: MemoryRepository,
        task_state_repo: SharedTaskStateRepository,
    ) -> None:
        extractor_mock.extract_from_output.return_value = [
            _insight("chose FastAPI", tags=["decision"])
        ]
        uc = ExtractInsightsUseCase(extractor_mock, memory_repo, task_state_repo)
        await uc.extract_and_store("t", AgentEngineType.CLAUDE_CODE, "o")
        saved = task_state_repo.save.call_args[0][0]
        assert len(saved.decisions) == 1
        assert saved.decisions[0].description == "chose FastAPI"

    @pytest.mark.anyio
    async def test_file_tagged_insight_adds_artifact(
        self,
        extractor_mock: InsightExtractorPort,
        memory_repo: MemoryRepository,
        task_state_repo: SharedTaskStateRepository,
    ) -> None:
        extractor_mock.extract_from_output.return_value = [
            _insight("created src/main.py", tags=["file"])
        ]
        uc = ExtractInsightsUseCase(extractor_mock, memory_repo, task_state_repo)
        await uc.extract_and_store("t", AgentEngineType.CLAUDE_CODE, "o")
        saved = task_state_repo.save.call_args[0][0]
        assert len(saved.artifacts) == 1

    @pytest.mark.anyio
    async def test_artifact_tagged_insight_adds_artifact(
        self,
        extractor_mock: InsightExtractorPort,
        memory_repo: MemoryRepository,
        task_state_repo: SharedTaskStateRepository,
    ) -> None:
        extractor_mock.extract_from_output.return_value = [
            _insight("generated report.pdf", tags=["artifact"])
        ]
        uc = ExtractInsightsUseCase(extractor_mock, memory_repo, task_state_repo)
        await uc.extract_and_store("t", AgentEngineType.CLAUDE_CODE, "o")
        saved = task_state_repo.save.call_args[0][0]
        assert len(saved.artifacts) == 1

    @pytest.mark.anyio
    async def test_conflict_resolution_removes_losers(
        self,
        memory_repo: MemoryRepository,
        task_state_repo: SharedTaskStateRepository,
    ) -> None:
        """When insights conflict, only winner gets stored."""
        a = _insight(
            "project uses Redis cache",
            engine=AgentEngineType.CLAUDE_CODE,
            confidence=0.9,
        )
        b = _insight(
            "project does not use Redis cache",
            engine=AgentEngineType.GEMINI_CLI,
            confidence=0.3,
        )
        extractor = AsyncMock(spec=InsightExtractorPort)
        extractor.extract_from_output.return_value = [a, b]
        uc = ExtractInsightsUseCase(extractor, memory_repo, task_state_repo)
        result = await uc.extract_and_store("t", AgentEngineType.CLAUDE_CODE, "o")
        assert len(result) == 1
        assert result[0].content == "project uses Redis cache"

    @pytest.mark.anyio
    async def test_multiple_insights_stored(
        self,
        memory_repo: MemoryRepository,
        task_state_repo: SharedTaskStateRepository,
    ) -> None:
        extractor = AsyncMock(spec=InsightExtractorPort)
        extractor.extract_from_output.return_value = [
            _insight("fact 1"),
            _insight("fact 2"),
            _insight("fact 3"),
        ]
        uc = ExtractInsightsUseCase(extractor, memory_repo, task_state_repo)
        result = await uc.extract_and_store("t", AgentEngineType.CLAUDE_CODE, "o")
        assert len(result) == 3
        assert memory_repo.add.call_count == 3

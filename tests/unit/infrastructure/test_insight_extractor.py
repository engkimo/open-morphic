"""Tests for InsightExtractor infrastructure."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from domain.ports.context_adapter import AdapterInsight, ContextAdapterPort
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.cognitive import CognitiveMemoryType
from infrastructure.cognitive.insight_extractor import InsightExtractor


def _adapter(
    engine: AgentEngineType,
    insights: list[AdapterInsight] | None = None,
) -> ContextAdapterPort:
    """Build a mock adapter returning the given insights."""
    mock = MagicMock(spec=ContextAdapterPort)
    mock.engine_type = engine
    mock.extract_insights.return_value = insights or []
    return mock


def _ai(
    content: str = "fact",
    mem_type: CognitiveMemoryType = CognitiveMemoryType.SEMANTIC,
    confidence: float = 0.7,
    tags: list[str] | None = None,
) -> AdapterInsight:
    return AdapterInsight(
        content=content,
        memory_type=mem_type,
        confidence=confidence,
        tags=tags or [],
    )


@pytest.fixture
def extractor() -> InsightExtractor:
    adapters = {
        AgentEngineType.CLAUDE_CODE: _adapter(
            AgentEngineType.CLAUDE_CODE,
            [_ai("uses PostgreSQL", CognitiveMemoryType.SEMANTIC, 0.8, ["fact"])],
        ),
        AgentEngineType.OLLAMA: _adapter(
            AgentEngineType.OLLAMA,
            [_ai("low confidence item", CognitiveMemoryType.EPISODIC, 0.3)],
        ),
    }
    return InsightExtractor(adapters=adapters)


class TestExtractFromOutput:
    """InsightExtractor.extract_from_output."""

    @pytest.mark.anyio
    async def test_returns_insights_for_known_engine(self, extractor: InsightExtractor) -> None:
        results = await extractor.extract_from_output(AgentEngineType.CLAUDE_CODE, "some output")
        assert len(results) == 1
        assert results[0].content == "uses PostgreSQL"
        assert results[0].source_engine == AgentEngineType.CLAUDE_CODE

    @pytest.mark.anyio
    async def test_unknown_engine_returns_empty(self, extractor: InsightExtractor) -> None:
        results = await extractor.extract_from_output(AgentEngineType.GEMINI_CLI, "some output")
        assert results == []

    @pytest.mark.anyio
    async def test_empty_output_returns_empty(self, extractor: InsightExtractor) -> None:
        results = await extractor.extract_from_output(AgentEngineType.CLAUDE_CODE, "")
        assert results == []

    @pytest.mark.anyio
    async def test_whitespace_output_returns_empty(self, extractor: InsightExtractor) -> None:
        results = await extractor.extract_from_output(AgentEngineType.CLAUDE_CODE, "   ")
        assert results == []

    @pytest.mark.anyio
    async def test_none_output_returns_empty(self, extractor: InsightExtractor) -> None:
        # Explicitly allow empty string edge case
        results = await extractor.extract_from_output(AgentEngineType.CLAUDE_CODE, "")
        assert results == []

    @pytest.mark.anyio
    async def test_deduplicates_by_normalised_content(self) -> None:
        adapter = _adapter(
            AgentEngineType.CLAUDE_CODE,
            [
                _ai("Uses Redis"),
                _ai("uses redis"),  # duplicate (case-insensitive)
                _ai("  Uses Redis  "),  # duplicate (whitespace)
            ],
        )
        ext = InsightExtractor(adapters={AgentEngineType.CLAUDE_CODE: adapter})
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "output")
        assert len(results) == 1

    @pytest.mark.anyio
    async def test_low_confidence_reclassified(self) -> None:
        """Adapter insights with confidence < 0.5 get reclassified."""
        adapter = _adapter(
            AgentEngineType.OLLAMA,
            [_ai("how to deploy the app", CognitiveMemoryType.EPISODIC, 0.3)],
        )
        ext = InsightExtractor(adapters={AgentEngineType.OLLAMA: adapter})
        results = await ext.extract_from_output(AgentEngineType.OLLAMA, "out")
        assert len(results) == 1
        # "how to" → PROCEDURAL via MemoryClassifier
        assert results[0].memory_type == CognitiveMemoryType.PROCEDURAL
        assert results[0].confidence >= 0.5

    @pytest.mark.anyio
    async def test_high_confidence_not_reclassified(self) -> None:
        """Adapter insights with confidence >= 0.5 keep their type."""
        adapter = _adapter(
            AgentEngineType.CLAUDE_CODE,
            [_ai("how to deploy", CognitiveMemoryType.EPISODIC, 0.8)],
        )
        ext = InsightExtractor(adapters={AgentEngineType.CLAUDE_CODE: adapter})
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "out")
        assert results[0].memory_type == CognitiveMemoryType.EPISODIC
        assert results[0].confidence == 0.8

    @pytest.mark.anyio
    async def test_tags_preserved(self) -> None:
        adapter = _adapter(
            AgentEngineType.CLAUDE_CODE,
            [_ai("created file x.py", CognitiveMemoryType.EPISODIC, 0.7, ["file", "code"])],
        )
        ext = InsightExtractor(adapters={AgentEngineType.CLAUDE_CODE: adapter})
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "out")
        assert results[0].tags == ["file", "code"]

    @pytest.mark.anyio
    async def test_source_engine_set_from_parameter(self) -> None:
        adapter = _adapter(
            AgentEngineType.GEMINI_CLI,
            [_ai("fact", CognitiveMemoryType.SEMANTIC, 0.7)],
        )
        ext = InsightExtractor(adapters={AgentEngineType.GEMINI_CLI: adapter})
        results = await ext.extract_from_output(AgentEngineType.GEMINI_CLI, "out")
        assert results[0].source_engine == AgentEngineType.GEMINI_CLI

    @pytest.mark.anyio
    async def test_adapter_returns_empty_list(self) -> None:
        adapter = _adapter(AgentEngineType.CLAUDE_CODE, [])
        ext = InsightExtractor(adapters={AgentEngineType.CLAUDE_CODE: adapter})
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "out")
        assert results == []

    @pytest.mark.anyio
    async def test_multiple_unique_insights(self) -> None:
        adapter = _adapter(
            AgentEngineType.CLAUDE_CODE,
            [
                _ai("uses Redis", CognitiveMemoryType.SEMANTIC, 0.8),
                _ai("decided to use FastAPI", CognitiveMemoryType.EPISODIC, 0.7),
                _ai("currently in progress", CognitiveMemoryType.WORKING, 0.6),
            ],
        )
        ext = InsightExtractor(adapters={AgentEngineType.CLAUDE_CODE: adapter})
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "out")
        assert len(results) == 3

    @pytest.mark.anyio
    async def test_empty_content_insight_skipped(self) -> None:
        adapter = _adapter(
            AgentEngineType.CLAUDE_CODE,
            [
                _ai("", CognitiveMemoryType.SEMANTIC, 0.7),
                _ai("real content", CognitiveMemoryType.SEMANTIC, 0.7),
            ],
        )
        ext = InsightExtractor(adapters={AgentEngineType.CLAUDE_CODE: adapter})
        results = await ext.extract_from_output(AgentEngineType.CLAUDE_CODE, "out")
        assert len(results) == 1
        assert results[0].content == "real content"

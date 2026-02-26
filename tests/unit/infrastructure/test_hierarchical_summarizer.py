"""Tests for infrastructure/memory/hierarchical_summarizer.py — HierarchicalSummaryManager.

Async tests using InMemoryMemoryRepository + FakeLLM.
"""

from __future__ import annotations

import json

import pytest

from domain.entities.memory import MemoryEntry
from domain.ports.llm_gateway import LLMGateway, LLMResponse
from domain.value_objects.status import MemoryType
from infrastructure.memory.hierarchical_summarizer import (
    _HIERARCHY_SUMMARIES_KEY,
    _HIERARCHY_TOKEN_COUNTS_KEY,
    HierarchicalSummaryManager,
    SummarizeResult,
)
from infrastructure.memory.memory_hierarchy import MemoryHierarchy
from infrastructure.persistence.in_memory import InMemoryMemoryRepository

# ── Fake LLM ──


class FakeLLM(LLMGateway):
    """Fake LLM that returns structured JSON summaries."""

    def __init__(self, response: str | None = None, should_fail: bool = False) -> None:
        self._response = response
        self._should_fail = should_fail

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        if self._should_fail:
            raise RuntimeError("LLM failure")
        content = self._response or json.dumps(
            {
                "1": "Level 1 summary.",
                "2": "Level 2 brief.",
                "3": "Topic.",
            }
        )
        return LLMResponse(
            content=content,
            model="fake-model",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.0,
        )

    async def is_available(self, model: str) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["fake-model"]


# ── Helpers ──


def _make_entry(content: str, entry_id: str = "entry-1") -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        content=content,
        memory_type=MemoryType.L2_SEMANTIC,
        metadata={},
    )


_LONG_TEXT = ". ".join(f"Sentence {i} with some details" for i in range(20)) + "."


# ── SummarizeResult ──


class TestSummarizeResult:
    def test_frozen(self) -> None:
        r = SummarizeResult(
            entry_id="a",
            levels_built=4,
            original_tokens=100,
            compressed_tokens=5,
            used_llm=False,
        )
        with pytest.raises(AttributeError):
            r.levels_built = 2  # type: ignore[misc]


# ── Summarize (Extractive, no LLM) ──


class TestSummarizeExtractive:
    @pytest.mark.asyncio()
    async def test_no_llm_uses_extractive(self) -> None:
        repo = InMemoryMemoryRepository()
        entry = _make_entry(_LONG_TEXT)
        await repo.add(entry)
        mgr = HierarchicalSummaryManager(memory_repo=repo)
        result = await mgr.summarize(entry.id)
        assert result is not None
        assert result.used_llm is False

    @pytest.mark.asyncio()
    async def test_levels_built_is_4(self) -> None:
        repo = InMemoryMemoryRepository()
        entry = _make_entry(_LONG_TEXT)
        await repo.add(entry)
        mgr = HierarchicalSummaryManager(memory_repo=repo)
        result = await mgr.summarize(entry.id)
        assert result is not None
        assert result.levels_built == 4

    @pytest.mark.asyncio()
    async def test_token_counts(self) -> None:
        repo = InMemoryMemoryRepository()
        entry = _make_entry(_LONG_TEXT)
        await repo.add(entry)
        mgr = HierarchicalSummaryManager(memory_repo=repo)
        result = await mgr.summarize(entry.id)
        assert result is not None
        assert result.original_tokens > 0
        assert result.compressed_tokens <= result.original_tokens

    @pytest.mark.asyncio()
    async def test_metadata_persisted(self) -> None:
        repo = InMemoryMemoryRepository()
        entry = _make_entry(_LONG_TEXT)
        await repo.add(entry)
        mgr = HierarchicalSummaryManager(memory_repo=repo)
        await mgr.summarize(entry.id)
        updated = await repo.get_by_id(entry.id)
        assert updated is not None
        assert _HIERARCHY_SUMMARIES_KEY in updated.metadata
        assert _HIERARCHY_TOKEN_COUNTS_KEY in updated.metadata

    @pytest.mark.asyncio()
    async def test_reread_summaries(self) -> None:
        repo = InMemoryMemoryRepository()
        entry = _make_entry(_LONG_TEXT)
        await repo.add(entry)
        mgr = HierarchicalSummaryManager(memory_repo=repo)
        await mgr.summarize(entry.id)
        updated = await repo.get_by_id(entry.id)
        assert updated is not None
        summaries = json.loads(updated.metadata[_HIERARCHY_SUMMARIES_KEY])
        assert "0" in summaries
        assert "3" in summaries
        assert len(summaries["0"]) >= len(summaries["3"])

    @pytest.mark.asyncio()
    async def test_not_found_returns_none(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = HierarchicalSummaryManager(memory_repo=repo)
        result = await mgr.summarize("nonexistent")
        assert result is None


# ── Summarize (LLM) ──


class TestSummarizeLLM:
    @pytest.mark.asyncio()
    async def test_with_llm(self) -> None:
        repo = InMemoryMemoryRepository()
        entry = _make_entry(_LONG_TEXT)
        await repo.add(entry)
        llm = FakeLLM()
        mgr = HierarchicalSummaryManager(memory_repo=repo, llm_gateway=llm)
        result = await mgr.summarize(entry.id)
        assert result is not None
        assert result.used_llm is True

    @pytest.mark.asyncio()
    async def test_llm_json_parsed(self) -> None:
        repo = InMemoryMemoryRepository()
        entry = _make_entry(_LONG_TEXT)
        await repo.add(entry)
        llm = FakeLLM()
        mgr = HierarchicalSummaryManager(memory_repo=repo, llm_gateway=llm)
        await mgr.summarize(entry.id)
        summary = await mgr.get_summary(entry.id, level=1)
        assert summary == "Level 1 summary."

    @pytest.mark.asyncio()
    async def test_llm_level3(self) -> None:
        repo = InMemoryMemoryRepository()
        entry = _make_entry(_LONG_TEXT)
        await repo.add(entry)
        llm = FakeLLM()
        mgr = HierarchicalSummaryManager(memory_repo=repo, llm_gateway=llm)
        await mgr.summarize(entry.id)
        summary = await mgr.get_summary(entry.id, level=3)
        assert summary == "Topic."

    @pytest.mark.asyncio()
    async def test_llm_error_falls_back_to_extractive(self) -> None:
        repo = InMemoryMemoryRepository()
        entry = _make_entry(_LONG_TEXT)
        await repo.add(entry)
        llm = FakeLLM(should_fail=True)
        mgr = HierarchicalSummaryManager(memory_repo=repo, llm_gateway=llm)
        result = await mgr.summarize(entry.id)
        assert result is not None
        assert result.used_llm is False
        assert result.levels_built == 4


# ── get_summary ──


class TestGetSummary:
    @pytest.mark.asyncio()
    async def test_not_found(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = HierarchicalSummaryManager(memory_repo=repo)
        assert await mgr.get_summary("missing") is None

    @pytest.mark.asyncio()
    async def test_not_summarized(self) -> None:
        repo = InMemoryMemoryRepository()
        entry = _make_entry("some content")
        await repo.add(entry)
        mgr = HierarchicalSummaryManager(memory_repo=repo)
        assert await mgr.get_summary(entry.id) is None

    @pytest.mark.asyncio()
    async def test_level0(self) -> None:
        repo = InMemoryMemoryRepository()
        entry = _make_entry(_LONG_TEXT)
        await repo.add(entry)
        mgr = HierarchicalSummaryManager(memory_repo=repo)
        await mgr.summarize(entry.id)
        result = await mgr.get_summary(entry.id, level=0)
        assert result == _LONG_TEXT

    @pytest.mark.asyncio()
    async def test_level3(self) -> None:
        repo = InMemoryMemoryRepository()
        entry = _make_entry(_LONG_TEXT)
        await repo.add(entry)
        mgr = HierarchicalSummaryManager(memory_repo=repo)
        await mgr.summarize(entry.id)
        result = await mgr.get_summary(entry.id, level=3)
        assert result is not None
        assert len(result) <= len(_LONG_TEXT)

    @pytest.mark.asyncio()
    async def test_invalid_level_clamped(self) -> None:
        repo = InMemoryMemoryRepository()
        entry = _make_entry(_LONG_TEXT)
        await repo.add(entry)
        mgr = HierarchicalSummaryManager(memory_repo=repo)
        await mgr.summarize(entry.id)
        # Level 99 should clamp to 3
        result = await mgr.get_summary(entry.id, level=99)
        assert result is not None


# ── retrieve_at_depth ──


class TestRetrieveAtDepth:
    @pytest.mark.asyncio()
    async def test_empty(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = HierarchicalSummaryManager(memory_repo=repo)
        result = await mgr.retrieve_at_depth("anything")
        assert result == ""

    @pytest.mark.asyncio()
    async def test_single_match(self) -> None:
        repo = InMemoryMemoryRepository()
        entry = _make_entry("The project budget is $54000 per year.")
        await repo.add(entry)
        mgr = HierarchicalSummaryManager(memory_repo=repo)
        await mgr.summarize(entry.id)
        result = await mgr.retrieve_at_depth("budget", max_tokens=500)
        assert "budget" in result.lower() or "$54000" in result

    @pytest.mark.asyncio()
    async def test_budget_selects_level(self) -> None:
        repo = InMemoryMemoryRepository()
        entry = _make_entry(_LONG_TEXT)
        await repo.add(entry)
        mgr = HierarchicalSummaryManager(memory_repo=repo)
        await mgr.summarize(entry.id)
        # Very small budget should get compressed version
        result_small = await mgr.retrieve_at_depth("sentence", max_tokens=20)
        # Large budget should get full version
        result_large = await mgr.retrieve_at_depth("sentence", max_tokens=5000)
        # Small result should be shorter or equal
        assert len(result_small) <= len(result_large)

    @pytest.mark.asyncio()
    async def test_multiple_entries_assembled(self) -> None:
        repo = InMemoryMemoryRepository()
        e1 = _make_entry("First topic about AI agents.", entry_id="e1")
        e2 = _make_entry("Second topic about memory systems.", entry_id="e2")
        await repo.add(e1)
        await repo.add(e2)
        mgr = HierarchicalSummaryManager(memory_repo=repo)
        await mgr.summarize(e1.id)
        await mgr.summarize(e2.id)
        result = await mgr.retrieve_at_depth("topic", max_tokens=5000)
        assert len(result) > 0


# ── Already Summarized ──


class TestAlreadySummarized:
    @pytest.mark.asyncio()
    async def test_skip_if_hierarchy_exists(self) -> None:
        repo = InMemoryMemoryRepository()
        entry = _make_entry(_LONG_TEXT)
        await repo.add(entry)
        mgr = HierarchicalSummaryManager(memory_repo=repo)
        r1 = await mgr.summarize(entry.id)
        r2 = await mgr.summarize(entry.id)
        assert r1 is not None
        assert r2 is not None
        # Second call should detect existing hierarchy
        assert r2.used_llm is False


# ── MemoryHierarchy Integration ──


class TestMemoryHierarchyIntegration:
    @pytest.mark.asyncio()
    async def test_summarize_entry(self) -> None:
        repo = InMemoryMemoryRepository()
        hierarchy = MemoryHierarchy(memory_repo=repo)
        await hierarchy.add(_LONG_TEXT)
        # Get the entry id from repo
        entries = await repo.list_by_type(MemoryType.L2_SEMANTIC)
        entry_id = entries[0].id
        result = await hierarchy.summarize_entry(entry_id)
        assert result["levels_built"] == 4

    @pytest.mark.asyncio()
    async def test_retrieve_at_depth(self) -> None:
        repo = InMemoryMemoryRepository()
        hierarchy = MemoryHierarchy(memory_repo=repo)
        await hierarchy.add(_LONG_TEXT)
        entries = await repo.list_by_type(MemoryType.L2_SEMANTIC)
        entry_id = entries[0].id
        await hierarchy.summarize_entry(entry_id)
        result = await hierarchy.retrieve_at_depth("sentence", max_tokens=500)
        assert len(result) > 0

    @pytest.mark.asyncio()
    async def test_coexistence_with_regular_memory(self) -> None:
        repo = InMemoryMemoryRepository()
        hierarchy = MemoryHierarchy(memory_repo=repo)
        # Add regular memory
        await hierarchy.add("regular conversation")
        # Add and summarize a memory
        await hierarchy.add(_LONG_TEXT)
        entries = await repo.list_by_type(MemoryType.L2_SEMANTIC)
        # Summarize the long one
        long_entry = [e for e in entries if len(e.content) > 100][0]
        await hierarchy.summarize_entry(long_entry.id)
        # Regular retrieve still works
        result = await hierarchy.retrieve("conversation")
        assert "regular conversation" in result
        # Depth-adaptive retrieve works
        depth_result = await hierarchy.retrieve_at_depth("sentence", max_tokens=500)
        assert len(depth_result) > 0

"""Tests for infrastructure/memory/delta_encoder.py — DeltaEncoderManager.

Async tests using InMemoryMemoryRepository.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from domain.entities.memory import MemoryEntry
from domain.value_objects.status import MemoryType
from infrastructure.memory.delta_encoder import (
    DeltaEncoderManager,
    DeltaRecordResult,
    _delta_to_entry,
    _entry_to_delta,
)
from infrastructure.memory.memory_hierarchy import MemoryHierarchy
from infrastructure.persistence.in_memory import InMemoryMemoryRepository


# ── DeltaRecordResult ──


class TestDeltaRecordResult:
    def test_frozen(self) -> None:
        r = DeltaRecordResult(delta_id="abc", topic="t", seq=0, state_hash="h")
        with pytest.raises(AttributeError):
            r.seq = 1  # type: ignore[misc]


# ── record ──


class TestRecord:
    @pytest.mark.asyncio()
    async def test_first_record_is_base(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        result = await mgr.record("project", "initial state", {"name": "Morphic"})
        assert result.seq == 0
        # Verify it's marked as base
        history = await mgr.get_history("project")
        assert history[0].is_base_state is True

    @pytest.mark.asyncio()
    async def test_seq_increments(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        r0 = await mgr.record("t", "first", {"a": 1})
        r1 = await mgr.record("t", "second", {"b": 2})
        r2 = await mgr.record("t", "third", {"c": 3})
        assert r0.seq == 0
        assert r1.seq == 1
        assert r2.seq == 2

    @pytest.mark.asyncio()
    async def test_result_fields(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        result = await mgr.record("mytopic", "init", {"x": 1})
        assert result.topic == "mytopic"
        assert len(result.delta_id) > 0
        assert len(result.state_hash) == 64

    @pytest.mark.asyncio()
    async def test_persisted_to_repo(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        result = await mgr.record("t", "msg", {"k": "v"})
        entry = await repo.get_by_id(result.delta_id)
        assert entry is not None
        assert entry.memory_type == MemoryType.L2_SEMANTIC

    @pytest.mark.asyncio()
    async def test_entry_content_is_message(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        result = await mgr.record("t", "my delta message", {"a": 1})
        entry = await repo.get_by_id(result.delta_id)
        assert entry is not None
        assert entry.content == "my delta message"

    @pytest.mark.asyncio()
    async def test_metadata_contains_delta_keys(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        result = await mgr.record("project", "init", {"name": "test"})
        entry = await repo.get_by_id(result.delta_id)
        assert entry is not None
        meta = entry.metadata
        assert meta["delta_topic"] == "project"
        assert meta["delta_seq"] == 0
        assert "delta_changes" in meta
        assert meta["delta_hash"] == result.state_hash
        assert meta["delta_is_base"] is True


# ── get_state ──


class TestGetState:
    @pytest.mark.asyncio()
    async def test_empty_topic_returns_empty(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        state = await mgr.get_state("nonexistent")
        assert state == {}

    @pytest.mark.asyncio()
    async def test_single_delta(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        await mgr.record("t", "init", {"a": 1, "b": 2})
        state = await mgr.get_state("t")
        assert state == {"a": 1, "b": 2}

    @pytest.mark.asyncio()
    async def test_multiple_deltas_accumulated(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        await mgr.record("t", "init", {"a": 1})
        await mgr.record("t", "add b", {"b": 2})
        await mgr.record("t", "add c", {"c": 3})
        state = await mgr.get_state("t")
        assert state == {"a": 1, "b": 2, "c": 3}

    @pytest.mark.asyncio()
    async def test_overwrite_key(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        await mgr.record("t", "init", {"status": "pending"})
        await mgr.record("t", "approve", {"status": "approved"})
        state = await mgr.get_state("t")
        assert state == {"status": "approved"}

    @pytest.mark.asyncio()
    async def test_tombstone_deletion(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        await mgr.record("t", "init", {"a": 1, "b": 2})
        await mgr.record("t", "remove b", {"b": None})
        state = await mgr.get_state("t")
        assert state == {"a": 1}

    @pytest.mark.asyncio()
    async def test_target_time(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)

        # Record first delta
        r1 = await mgr.record("t", "init", {"a": 1})

        # Get the created_at of the first delta to use as cutoff
        history = await mgr.get_history("t")
        cutoff = history[0].created_at + timedelta(seconds=1)

        # Record second delta with future timestamp
        r2 = await mgr.record("t", "add b", {"b": 2})
        # Manually adjust second entry's timestamp to future
        entry = await repo.get_by_id(r2.delta_id)
        assert entry is not None
        future_time = datetime.now() + timedelta(hours=10)
        updated = MemoryEntry(
            id=entry.id,
            content=entry.content,
            memory_type=entry.memory_type,
            access_count=entry.access_count,
            importance_score=entry.importance_score,
            metadata=entry.metadata,
            created_at=future_time,
            last_accessed=future_time,
        )
        # Replace entry in repo
        await repo.delete(entry.id)
        await repo.add(updated)

        state = await mgr.get_state("t", target_time=cutoff)
        assert state == {"a": 1}


# ── get_history ──


class TestGetHistory:
    @pytest.mark.asyncio()
    async def test_empty(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        history = await mgr.get_history("nonexistent")
        assert history == []

    @pytest.mark.asyncio()
    async def test_ordered_by_seq(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        await mgr.record("t", "first", {"a": 1})
        await mgr.record("t", "second", {"b": 2})
        await mgr.record("t", "third", {"c": 3})
        history = await mgr.get_history("t")
        assert len(history) == 3
        assert [d.seq for d in history] == [0, 1, 2]
        assert [d.message for d in history] == ["first", "second", "third"]

    @pytest.mark.asyncio()
    async def test_all_deltas_included(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        for i in range(5):
            await mgr.record("t", f"delta {i}", {f"key{i}": i})
        history = await mgr.get_history("t")
        assert len(history) == 5

    @pytest.mark.asyncio()
    async def test_topic_isolation(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        await mgr.record("alpha", "a1", {"x": 1})
        await mgr.record("alpha", "a2", {"y": 2})
        await mgr.record("beta", "b1", {"z": 3})
        alpha = await mgr.get_history("alpha")
        beta = await mgr.get_history("beta")
        assert len(alpha) == 2
        assert len(beta) == 1


# ── list_topics ──


class TestListTopics:
    @pytest.mark.asyncio()
    async def test_empty(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        topics = await mgr.list_topics()
        assert topics == []

    @pytest.mark.asyncio()
    async def test_unique_topics(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        await mgr.record("alpha", "init", {"a": 1})
        await mgr.record("beta", "init", {"b": 1})
        topics = await mgr.list_topics()
        assert set(topics) == {"alpha", "beta"}

    @pytest.mark.asyncio()
    async def test_ignores_non_delta_entries(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        # Add a regular (non-delta) memory entry
        regular = MemoryEntry(
            content="regular memory",
            memory_type=MemoryType.L2_SEMANTIC,
            metadata={"role": "user"},
        )
        await repo.add(regular)
        await mgr.record("project", "init", {"name": "test"})
        topics = await mgr.list_topics()
        assert topics == ["project"]

    @pytest.mark.asyncio()
    async def test_deduplicates(self) -> None:
        repo = InMemoryMemoryRepository()
        mgr = DeltaEncoderManager(memory_repo=repo)
        await mgr.record("same", "first", {"a": 1})
        await mgr.record("same", "second", {"b": 2})
        await mgr.record("same", "third", {"c": 3})
        topics = await mgr.list_topics()
        assert topics == ["same"]


# ── Roundtrip Delta ↔ Entry ──


class TestRoundtrip:
    def test_delta_entry_roundtrip(self) -> None:
        from domain.services.delta_encoder import DeltaEncoder

        delta = DeltaEncoder.create_delta("proj", 3, "update budget", {"budget": 54000})
        entry = _delta_to_entry(delta)
        recovered = _entry_to_delta(entry)
        assert recovered is not None
        assert recovered.topic == delta.topic
        assert recovered.seq == delta.seq
        assert recovered.message == delta.message
        assert recovered.changes == delta.changes
        assert recovered.state_hash == delta.state_hash
        assert recovered.is_base_state == delta.is_base_state

    def test_non_delta_entry_returns_none(self) -> None:
        entry = MemoryEntry(
            content="not a delta",
            memory_type=MemoryType.L2_SEMANTIC,
            metadata={"role": "user"},
        )
        assert _entry_to_delta(entry) is None


# ── MemoryHierarchy integration ──


class TestMemoryHierarchyDelta:
    @pytest.mark.asyncio()
    async def test_record_delta(self) -> None:
        repo = InMemoryMemoryRepository()
        hierarchy = MemoryHierarchy(memory_repo=repo)
        result = await hierarchy.record_delta("proj", "init", {"name": "Morphic"})
        assert result["topic"] == "proj"
        assert result["seq"] == 0

    @pytest.mark.asyncio()
    async def test_get_state(self) -> None:
        repo = InMemoryMemoryRepository()
        hierarchy = MemoryHierarchy(memory_repo=repo)
        await hierarchy.record_delta("proj", "init", {"name": "Morphic"})
        await hierarchy.record_delta("proj", "set budget", {"budget": 50000})
        state = await hierarchy.get_state("proj")
        assert state == {"name": "Morphic", "budget": 50000}

    @pytest.mark.asyncio()
    async def test_get_state_history(self) -> None:
        repo = InMemoryMemoryRepository()
        hierarchy = MemoryHierarchy(memory_repo=repo)
        await hierarchy.record_delta("proj", "init", {"a": 1})
        await hierarchy.record_delta("proj", "update", {"b": 2})
        history = await hierarchy.get_state_history("proj")
        assert len(history) == 2
        assert history[0]["message"] == "init"
        assert history[1]["message"] == "update"

    @pytest.mark.asyncio()
    async def test_coexistence_with_regular_memory(self) -> None:
        """Delta entries coexist with regular memory entries."""
        repo = InMemoryMemoryRepository()
        hierarchy = MemoryHierarchy(memory_repo=repo)
        # Add regular memory
        await hierarchy.add("regular conversation", role="user")
        # Add delta
        await hierarchy.record_delta("proj", "init", {"x": 1})
        # Both work independently
        state = await hierarchy.get_state("proj")
        assert state == {"x": 1}
        # Regular memory retrieval still works
        result = await hierarchy.retrieve("conversation")
        assert "regular conversation" in result

"""Tests for domain/services/delta_encoder.py and domain/entities/delta.py.

Pure logic tests — no I/O, no async.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

import pytest

from domain.entities.delta import Delta
from domain.services.delta_encoder import DeltaEncoder


# ── Delta Entity ──


class TestDeltaEntity:
    def test_auto_id_and_timestamp(self) -> None:
        d = Delta(
            topic="t",
            seq=0,
            message="init",
            changes={"a": 1},
            state_hash="abc",
        )
        assert len(d.id) > 0
        assert isinstance(d.created_at, datetime)

    def test_strict_validation_rejects_bad_types(self) -> None:
        with pytest.raises(Exception):
            Delta(
                topic="t",
                seq="not_int",  # type: ignore[arg-type]
                message="init",
                changes={"a": 1},
                state_hash="abc",
            )

    def test_empty_topic_rejected(self) -> None:
        with pytest.raises(Exception):
            Delta(topic="", seq=0, message="m", changes={"a": 1}, state_hash="h")

    def test_empty_message_rejected(self) -> None:
        with pytest.raises(Exception):
            Delta(topic="t", seq=0, message="", changes={"a": 1}, state_hash="h")

    def test_empty_changes_rejected(self) -> None:
        with pytest.raises(Exception):
            Delta(topic="t", seq=0, message="m", changes={}, state_hash="h")

    def test_negative_seq_rejected(self) -> None:
        with pytest.raises(Exception):
            Delta(topic="t", seq=-1, message="m", changes={"a": 1}, state_hash="h")

    def test_is_base_state_default_false(self) -> None:
        d = Delta(topic="t", seq=0, message="m", changes={"a": 1}, state_hash="h")
        assert d.is_base_state is False


# ── hash_changes ──


class TestHashChanges:
    def test_deterministic(self) -> None:
        h1 = DeltaEncoder.hash_changes({"a": 1, "b": 2})
        h2 = DeltaEncoder.hash_changes({"a": 1, "b": 2})
        assert h1 == h2

    def test_order_irrelevant(self) -> None:
        h1 = DeltaEncoder.hash_changes({"z": 1, "a": 2})
        h2 = DeltaEncoder.hash_changes({"a": 2, "z": 1})
        assert h1 == h2

    def test_different_values_different_hash(self) -> None:
        h1 = DeltaEncoder.hash_changes({"a": 1})
        h2 = DeltaEncoder.hash_changes({"a": 2})
        assert h1 != h2

    def test_unicode_support(self) -> None:
        h = DeltaEncoder.hash_changes({"key": "日本語テスト"})
        assert isinstance(h, str)
        assert len(h) == 64

    def test_hex_format_64_chars(self) -> None:
        h = DeltaEncoder.hash_changes({"x": 42})
        assert re.fullmatch(r"[0-9a-f]{64}", h)

    def test_nested_dict(self) -> None:
        h = DeltaEncoder.hash_changes({"nested": {"a": 1, "b": [1, 2]}})
        assert len(h) == 64


# ── reconstruct ──


class TestReconstruct:
    def test_empty_deltas_returns_base(self) -> None:
        base = {"a": 1, "b": 2}
        result = DeltaEncoder.reconstruct(base, [])
        assert result == {"a": 1, "b": 2}

    def test_single_delta(self) -> None:
        base = {"a": 1}
        d = DeltaEncoder.create_delta("t", 0, "add b", {"b": 2})
        result = DeltaEncoder.reconstruct(base, [d])
        assert result == {"a": 1, "b": 2}

    def test_multiple_deltas(self) -> None:
        base = {"a": 1}
        d1 = DeltaEncoder.create_delta("t", 0, "add b", {"b": 2})
        d2 = DeltaEncoder.create_delta("t", 1, "add c", {"c": 3})
        result = DeltaEncoder.reconstruct(base, [d1, d2])
        assert result == {"a": 1, "b": 2, "c": 3}

    def test_overwrite_existing_key(self) -> None:
        base = {"a": 1}
        d = DeltaEncoder.create_delta("t", 0, "change a", {"a": 99})
        result = DeltaEncoder.reconstruct(base, [d])
        assert result == {"a": 99}

    def test_target_time_filters_deltas(self) -> None:
        base = {"a": 1}
        now = datetime.now()
        past = now - timedelta(hours=2)
        future = now + timedelta(hours=2)

        d1 = DeltaEncoder.create_delta("t", 0, "early", {"b": 2})
        # Manually set created_at for deterministic testing
        d1 = d1.model_copy(update={"created_at": past})

        d2 = DeltaEncoder.create_delta("t", 1, "late", {"c": 3})
        d2 = d2.model_copy(update={"created_at": future})

        # target_time=now → only d1 applied
        result = DeltaEncoder.reconstruct(base, [d1, d2], target_time=now)
        assert result == {"a": 1, "b": 2}

    def test_unsorted_deltas_sorted_by_seq(self) -> None:
        base = {"val": 0}
        d2 = DeltaEncoder.create_delta("t", 2, "third", {"val": 3})
        d0 = DeltaEncoder.create_delta("t", 0, "first", {"val": 1})
        d1 = DeltaEncoder.create_delta("t", 1, "second", {"val": 2})
        # Pass out of order
        result = DeltaEncoder.reconstruct(base, [d2, d0, d1])
        # Last applied (seq=2) wins
        assert result == {"val": 3}

    def test_tombstone_removes_key(self) -> None:
        base = {"a": 1, "b": 2}
        d = DeltaEncoder.create_delta("t", 0, "remove b", {"b": None})
        result = DeltaEncoder.reconstruct(base, [d])
        assert result == {"a": 1}

    def test_tombstone_nonexistent_key_is_noop(self) -> None:
        base = {"a": 1}
        d = DeltaEncoder.create_delta("t", 0, "remove z", {"z": None})
        result = DeltaEncoder.reconstruct(base, [d])
        assert result == {"a": 1}

    def test_base_state_not_mutated(self) -> None:
        base = {"a": 1}
        d = DeltaEncoder.create_delta("t", 0, "add b", {"b": 2})
        DeltaEncoder.reconstruct(base, [d])
        assert base == {"a": 1}

    def test_empty_base_and_deltas(self) -> None:
        result = DeltaEncoder.reconstruct({}, [])
        assert result == {}


# ── create_delta ──


class TestCreateDelta:
    def test_hash_computed(self) -> None:
        d = DeltaEncoder.create_delta("t", 0, "msg", {"a": 1})
        expected = DeltaEncoder.hash_changes({"a": 1})
        assert d.state_hash == expected

    def test_base_flag(self) -> None:
        d = DeltaEncoder.create_delta("t", 0, "base", {"a": 1}, is_base=True)
        assert d.is_base_state is True

    def test_auto_id(self) -> None:
        d = DeltaEncoder.create_delta("t", 0, "msg", {"a": 1})
        assert len(d.id) > 0

    def test_auto_timestamp(self) -> None:
        before = datetime.now()
        d = DeltaEncoder.create_delta("t", 0, "msg", {"a": 1})
        after = datetime.now()
        assert before <= d.created_at <= after


# ── compute_diff ──


class TestComputeDiff:
    def test_identical_states(self) -> None:
        diff = DeltaEncoder.compute_diff({"a": 1}, {"a": 1})
        assert diff == {}

    def test_added_key(self) -> None:
        diff = DeltaEncoder.compute_diff({"a": 1}, {"a": 1, "b": 2})
        assert diff == {"b": 2}

    def test_changed_value(self) -> None:
        diff = DeltaEncoder.compute_diff({"a": 1}, {"a": 99})
        assert diff == {"a": 99}

    def test_removed_key_tombstone(self) -> None:
        diff = DeltaEncoder.compute_diff({"a": 1, "b": 2}, {"a": 1})
        assert diff == {"b": None}

    def test_mixed_add_change_remove(self) -> None:
        old = {"a": 1, "b": 2, "c": 3}
        new = {"a": 1, "b": 99, "d": 4}
        diff = DeltaEncoder.compute_diff(old, new)
        assert diff == {"b": 99, "c": None, "d": 4}

    def test_empty_to_populated(self) -> None:
        diff = DeltaEncoder.compute_diff({}, {"x": 1, "y": 2})
        assert diff == {"x": 1, "y": 2}

    def test_populated_to_empty(self) -> None:
        diff = DeltaEncoder.compute_diff({"x": 1, "y": 2}, {})
        assert diff == {"x": None, "y": None}

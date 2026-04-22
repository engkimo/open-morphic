"""DeltaEncoder — Git-style delta state tracking.

Pure domain service: no I/O, no external deps beyond stdlib.
All methods are static — follows ForgettingCurve pattern.

State is tracked as key-value dicts. Deltas record changes between states.
Tombstone deletion: a key set to None means "deleted from state".
Hash: SHA-256 of json.dumps(sort_keys=True) — deterministic per Manus principle 1.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from domain.entities.delta import Delta


class DeltaEncoder:
    """Static methods for delta state tracking — no state, pure functions."""

    @staticmethod
    def hash_changes(changes: dict[str, Any]) -> str:
        """Compute deterministic SHA-256 hex digest of changes dict.

        Uses json.dumps with sort_keys=True for order-independence.
        """
        serialized = json.dumps(changes, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def reconstruct(
        base_state: dict[str, Any],
        deltas: list[Delta],
        target_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Reconstruct state by applying deltas in seq order.

        Args:
            base_state: Initial state dict.
            deltas: List of Delta entities (will be sorted by seq).
            target_time: If provided, only apply deltas created at or before this time.

        Returns:
            Reconstructed state dict. Keys with None values (tombstones) are removed.
        """
        state = dict(base_state)

        sorted_deltas = sorted(deltas, key=lambda d: d.seq)

        for delta in sorted_deltas:
            if target_time is not None and delta.created_at > target_time:
                break
            for key, value in delta.changes.items():
                if value is None:
                    state.pop(key, None)
                else:
                    state[key] = value

        return state

    @staticmethod
    def create_delta(
        topic: str,
        seq: int,
        message: str,
        changes: dict[str, Any],
        is_base: bool = False,
    ) -> Delta:
        """Factory to create a Delta with auto-computed hash, id, and timestamp."""
        state_hash = DeltaEncoder.hash_changes(changes)
        return Delta(
            topic=topic,
            seq=seq,
            message=message,
            changes=changes,
            state_hash=state_hash,
            is_base_state=is_base,
        )

    @staticmethod
    def compute_diff(
        old_state: dict[str, Any],
        new_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Compute minimal diff between two states.

        - Added keys: present in new, absent in old.
        - Changed keys: present in both, different values.
        - Removed keys: present in old, absent in new → value is None (tombstone).

        Returns empty dict if states are identical.
        """
        diff: dict[str, Any] = {}

        for key, value in new_state.items():
            if key not in old_state or old_state[key] != value:
                diff[key] = value

        for key in old_state:
            if key not in new_state:
                diff[key] = None

        return diff

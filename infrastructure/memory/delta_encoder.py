"""DeltaEncoderManager — async manager for Git-style delta state tracking.

Persists Delta entities as MemoryEntry (L2_SEMANTIC) with delta metadata.
No new ports needed — reuses existing MemoryRepository.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from domain.entities.delta import Delta
from domain.entities.memory import MemoryEntry
from domain.ports.memory_repository import MemoryRepository
from domain.services.delta_encoder import DeltaEncoder
from domain.value_objects.status import MemoryType

_DELTA_TOPIC_KEY = "delta_topic"
_DELTA_SEQ_KEY = "delta_seq"
_DELTA_CHANGES_KEY = "delta_changes"
_DELTA_HASH_KEY = "delta_hash"
_DELTA_IS_BASE_KEY = "delta_is_base"


@dataclass(frozen=True)
class DeltaRecordResult:
    """Result returned from record()."""

    delta_id: str
    topic: str
    seq: int
    state_hash: str


def _delta_to_entry(delta: Delta) -> MemoryEntry:
    """Serialize a Delta into a MemoryEntry for persistence."""
    return MemoryEntry(
        id=delta.id,
        content=delta.message,
        memory_type=MemoryType.L2_SEMANTIC,
        metadata={
            _DELTA_TOPIC_KEY: delta.topic,
            _DELTA_SEQ_KEY: delta.seq,
            _DELTA_CHANGES_KEY: json.dumps(
                delta.changes,
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            ),
            _DELTA_HASH_KEY: delta.state_hash,
            _DELTA_IS_BASE_KEY: delta.is_base_state,
        },
        created_at=delta.created_at,
        last_accessed=delta.created_at,
    )


def _entry_to_delta(entry: MemoryEntry) -> Delta | None:
    """Deserialize a MemoryEntry back into a Delta. Returns None if not a delta entry."""
    meta = entry.metadata
    if _DELTA_TOPIC_KEY not in meta:
        return None
    return Delta(
        id=entry.id,
        topic=meta[_DELTA_TOPIC_KEY],
        seq=meta[_DELTA_SEQ_KEY],
        message=entry.content,
        changes=json.loads(meta[_DELTA_CHANGES_KEY]),
        state_hash=meta[_DELTA_HASH_KEY],
        is_base_state=meta.get(_DELTA_IS_BASE_KEY, False),
        created_at=entry.created_at,
    )


class DeltaEncoderManager:
    """Async manager for recording and reconstructing delta state.

    Stores deltas as MemoryEntry (L2_SEMANTIC) with delta_* metadata keys.
    Uses domain DeltaEncoder for pure hash/reconstruct logic.
    """

    def __init__(self, memory_repo: MemoryRepository) -> None:
        self._memory_repo = memory_repo

    async def record(
        self,
        topic: str,
        message: str,
        changes: dict[str, Any],
    ) -> DeltaRecordResult:
        """Record a new delta for the given topic.

        Auto-assigns seq number (0 for first, incrementing).
        First delta is automatically marked as base state.
        """
        existing = await self._get_deltas_for_topic(topic)
        seq = len(existing)
        is_base = seq == 0

        delta = DeltaEncoder.create_delta(
            topic=topic,
            seq=seq,
            message=message,
            changes=changes,
            is_base=is_base,
        )

        entry = _delta_to_entry(delta)
        await self._memory_repo.add(entry)

        return DeltaRecordResult(
            delta_id=delta.id,
            topic=delta.topic,
            seq=delta.seq,
            state_hash=delta.state_hash,
        )

    async def get_state(
        self,
        topic: str,
        target_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Reconstruct current (or historical) state for a topic."""
        deltas = await self._get_deltas_for_topic(topic)
        return DeltaEncoder.reconstruct({}, deltas, target_time=target_time)

    async def get_history(self, topic: str) -> list[Delta]:
        """Get full delta chain for a topic, ordered by seq."""
        deltas = await self._get_deltas_for_topic(topic)
        return sorted(deltas, key=lambda d: d.seq)

    async def list_topics(self) -> list[str]:
        """List all unique delta topics."""
        entries = await self._memory_repo.list_by_type(MemoryType.L2_SEMANTIC)
        topics: list[str] = []
        seen: set[str] = set()
        for entry in entries:
            topic = entry.metadata.get(_DELTA_TOPIC_KEY)
            if topic is not None and topic not in seen:
                seen.add(topic)
                topics.append(topic)
        return topics

    async def _get_deltas_for_topic(self, topic: str) -> list[Delta]:
        """Fetch all delta entries for a topic from the repository."""
        entries = await self._memory_repo.list_by_type(MemoryType.L2_SEMANTIC)
        deltas: list[Delta] = []
        for entry in entries:
            if entry.metadata.get(_DELTA_TOPIC_KEY) == topic:
                delta = _entry_to_delta(entry)
                if delta is not None:
                    deltas.append(delta)
        return deltas

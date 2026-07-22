"""Bounded resumable checkpoint catch-up with durable trust-pinned audit."""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import stat
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.agent_cli_checkpoint_registry import (
    CheckpointRegistrySnapshot,
    CheckpointRegistryStore,
    SignedCheckpointRangeBundle,
)
from benchmarks.agent_cli_comparison import SCHEMA_VERSION
from benchmarks.agent_cli_gossip import (
    fetch_checkpoint_gossip_status,
    fetch_signed_checkpoint_range,
)
from benchmarks.agent_cli_peer_trust_ledger import CheckpointPeerTrustLedger
from benchmarks.agent_cli_transparency import SignedAuthorityRootLedger
from benchmarks.agent_cli_witness import TransparencyWitnessTrust

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_SyncEvent = Literal["imported", "recovered", "retry", "stopped", "trust_advanced"]
_StopReason = Literal[
    "up_to_date",
    "range_gap",
    "record_budget_exhausted",
    "round_budget_exhausted",
    "retry_exhausted",
]
_TransportOperation = Literal["status", "fetch_range"]


class _FrozenModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid", frozen=True)


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _canonical_sha256(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _validate_identifier(identifier: str, *, label: str) -> None:
    if not identifier or identifier != identifier.strip():
        raise ValueError(f"{label} must be non-blank without surrounding whitespace")


class CheckpointGossipSyncPolicy(_FrozenModel):
    max_rounds: int = Field(default=16, ge=1, le=100)
    max_records: int = Field(default=1000, ge=1, le=10_000)
    max_attempts_per_request: int = Field(default=3, ge=1, le=10)
    retry_delays_seconds: tuple[float, ...] = (0.05, 0.1)

    @model_validator(mode="after")
    def validate_policy(self) -> CheckpointGossipSyncPolicy:
        expected = self.max_attempts_per_request - 1
        if len(self.retry_delays_seconds) != expected:
            raise ValueError("retry delay count must be max attempts minus one")
        if any(delay < 0 or delay > 5 for delay in self.retry_delays_seconds):
            raise ValueError("retry delays must be between zero and five seconds")
        if sum(self.retry_delays_seconds) > 30:
            raise ValueError("total retry delay must not exceed 30 seconds")
        return self

    @property
    def policy_sha256(self) -> str:
        return _canonical_sha256(self.model_dump(mode="json"))


class CheckpointGossipSyncAuditRecord(_FrozenModel):
    schema_version: int
    registry_id: str = Field(min_length=1, max_length=200)
    source_peer_id: str = Field(min_length=1, max_length=200)
    audit_sequence: int = Field(ge=0)
    previous_record_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    event: _SyncEvent
    peer_trust_generation: int = Field(ge=1)
    peer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    peer_trust_ledger_sha256: str = Field(pattern=_SHA256_PATTERN)
    sync_policy_sha256: str = Field(pattern=_SHA256_PATTERN)
    local_record_count: int = Field(ge=0)
    local_head_record_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    range_bundle_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    first_sequence: int | None = Field(default=None, ge=0)
    last_sequence: int | None = Field(default=None, ge=0)
    imported_records: int = Field(default=0, ge=0)
    transport_operation: _TransportOperation | None = None
    transport_attempt: int | None = Field(default=None, ge=1, le=10)
    stop_reason: _StopReason | None = None
    record_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_record(self) -> CheckpointGossipSyncAuditRecord:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.registry_id, label="registry_id")
        _validate_identifier(self.source_peer_id, label="source_peer_id")
        if (self.local_record_count == 0) != (
            self.local_head_record_sha256 is None
        ):
            raise ValueError("sync audit local head does not match record count")
        range_fields = (
            self.range_bundle_sha256,
            self.first_sequence,
            self.last_sequence,
        )
        if self.event == "imported":
            if any(value is None for value in range_fields) or self.imported_records < 1:
                raise ValueError("imported sync audit record is incomplete")
            assert self.first_sequence is not None
            assert self.last_sequence is not None
            if self.first_sequence > self.last_sequence:
                raise ValueError("imported sync audit range is inverted")
        elif any(value is not None for value in range_fields) or self.imported_records:
            raise ValueError("non-import sync audit record carries range metadata")
        if self.event == "retry":
            if self.transport_operation is None or self.transport_attempt is None:
                raise ValueError("retry sync audit record is incomplete")
        elif self.transport_operation is not None or self.transport_attempt is not None:
            raise ValueError("non-retry sync audit record carries retry metadata")
        if (self.event == "stopped") != (self.stop_reason is not None):
            raise ValueError("sync audit stop reason does not match event")
        if self.record_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("sync audit record fingerprint does not match")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"record_sha256"})

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class CheckpointGossipSyncAuditSnapshot(_FrozenModel):
    schema_version: int
    registry_id: str
    source_peer_id: str
    records: tuple[CheckpointGossipSyncAuditRecord, ...]
    record_count: int = Field(ge=0)
    head_record_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    local_record_count: int = Field(ge=0)
    local_head_record_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    peer_trust_generation: int | None = Field(default=None, ge=1)
    peer_trust_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_snapshot(self) -> CheckpointGossipSyncAuditSnapshot:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if self.record_count != len(self.records):
            raise ValueError("sync audit snapshot record count does not match")
        last = self.records[-1] if self.records else None
        expected = (
            last.record_sha256 if last else None,
            last.local_record_count if last else 0,
            last.local_head_record_sha256 if last else None,
            last.peer_trust_generation if last else None,
            last.peer_trust_sha256 if last else None,
        )
        actual = (
            self.head_record_sha256,
            self.local_record_count,
            self.local_head_record_sha256,
            self.peer_trust_generation,
            self.peer_trust_sha256,
        )
        if actual != expected:
            raise ValueError("sync audit snapshot head metadata does not match records")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class CheckpointGossipSyncResult(_FrozenModel):
    schema_version: int
    registry_id: str
    source_peer_id: str
    stop_reason: _StopReason
    rounds_attempted: int = Field(ge=0)
    ranges_imported: int = Field(ge=0)
    records_imported: int = Field(ge=0)
    retries: int = Field(ge=0)
    local_record_count: int = Field(ge=0)
    local_head_record_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    peer_trust_generation: int = Field(ge=1)
    peer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    sync_policy_sha256: str = Field(pattern=_SHA256_PATTERN)
    sync_audit_head_sha256: str = Field(pattern=_SHA256_PATTERN)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class _AvailableRange(_FrozenModel):
    first_sequence: int = Field(ge=0)
    last_sequence: int = Field(ge=0)
    range_bundle_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_range(self) -> _AvailableRange:
        if self.first_sequence > self.last_sequence:
            raise ValueError("checkpoint gossip status range is inverted")
        return self


class _GossipStatus(_FrozenModel):
    registry_id: str
    source_peer_id: str
    available_ranges: tuple[_AvailableRange, ...]

    @model_validator(mode="after")
    def validate_status(self) -> _GossipStatus:
        starts = [item.first_sequence for item in self.available_ranges]
        if starts != sorted(starts) or len(starts) != len(set(starts)):
            raise ValueError("checkpoint gossip status ranges must be sorted and unique")
        return self


class CheckpointGossipSyncAuditStore:
    """Single-writer append-only audit for one registry/source pull loop."""

    def __init__(
        self,
        path: str | Path,
        *,
        registry_id: str,
        source_peer_id: str,
    ) -> None:
        self.path = Path(path)
        _validate_identifier(registry_id, label="registry_id")
        _validate_identifier(source_peer_id, label="source_peer_id")
        self.registry_id = registry_id
        self.source_peer_id = source_peer_id

    def _open(self, *, create: bool) -> int | None:
        flags = (
            os.O_RDWR if create else os.O_RDONLY
        ) | getattr(os, "O_NOFOLLOW", 0)
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            flags |= os.O_CREAT | os.O_APPEND
        try:
            descriptor = os.open(self.path, flags, 0o600)
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise ValueError("sync audit ledger must be a regular file")
        if create:
            os.fchmod(descriptor, 0o600)
        return descriptor

    @contextmanager
    def locked(self) -> Iterator[_CheckpointGossipSyncAuditWriter]:
        descriptor = self._open(create=True)
        assert descriptor is not None
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("checkpoint gossip sync is already running") from exc
            yield _CheckpointGossipSyncAuditWriter(self, descriptor)
        finally:
            os.close(descriptor)

    def replay(
        self,
        peer_trust_ledger: CheckpointPeerTrustLedger,
    ) -> CheckpointGossipSyncAuditSnapshot:
        descriptor = self._open(create=False)
        if descriptor is None:
            return self._snapshot(())
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH)
            records = self._read_records(descriptor, peer_trust_ledger)
            return self._snapshot(records)
        finally:
            os.close(descriptor)

    def _read_records(
        self,
        descriptor: int,
        peer_trust_ledger: CheckpointPeerTrustLedger,
    ) -> tuple[CheckpointGossipSyncAuditRecord, ...]:
        ledger = CheckpointPeerTrustLedger.model_validate(
            peer_trust_ledger.model_dump(mode="json")
        )
        size = os.fstat(descriptor).st_size
        raw = os.pread(descriptor, size, 0)
        if not raw:
            return ()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("sync audit ledger must be UTF-8 JSONL") from exc
        if not text.endswith("\n"):
            raise ValueError("sync audit ledger has a truncated final record")
        records: list[CheckpointGossipSyncAuditRecord] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            try:
                record = CheckpointGossipSyncAuditRecord.model_validate_json(line)
            except ValueError as exc:
                raise ValueError(
                    f"invalid sync audit record at line {line_number}: {exc}"
                ) from exc
            if (
                record.registry_id != self.registry_id
                or record.source_peer_id != self.source_peer_id
            ):
                raise ValueError("sync audit record endpoint does not match store")
            if record.audit_sequence != len(records):
                raise ValueError("sync audit sequence is not contiguous")
            expected_previous = records[-1].record_sha256 if records else None
            if record.previous_record_sha256 != expected_previous:
                raise ValueError("sync audit hash chain is invalid")
            if records:
                previous = records[-1]
                if record.local_record_count < previous.local_record_count:
                    raise ValueError("sync audit local record count regressed")
                if record.peer_trust_generation < previous.peer_trust_generation:
                    raise ValueError("sync audit peer trust generation regressed")
                if record.event == "imported":
                    if record.local_record_count != (
                        previous.local_record_count + record.imported_records
                    ):
                        raise ValueError("sync audit imported record count does not advance")
                elif record.event != "recovered" and (
                    record.local_record_count != previous.local_record_count
                    or record.local_head_record_sha256
                    != previous.local_head_record_sha256
                ):
                    raise ValueError("sync audit non-import event changes registry head")
            if record.peer_trust_generation > ledger.active_generation:
                raise ValueError("peer trust ledger rollback detected by sync audit pin")
            pinned_generation = ledger.generations[record.peer_trust_generation - 1]
            if pinned_generation.trust.peer_trust_sha256 != record.peer_trust_sha256:
                raise ValueError("peer trust ledger fork detected at sync audit pin")
            if (
                record.peer_trust_generation == ledger.active_generation
                and record.peer_trust_ledger_sha256 != ledger.ledger_sha256
            ):
                raise ValueError("peer trust ledger fork detected at active generation")
            records.append(record)
        if records and ledger.active_generation < records[-1].peer_trust_generation:
            raise ValueError("peer trust ledger rollback detected by sync audit pin")
        return tuple(records)

    def _snapshot(
        self,
        records: tuple[CheckpointGossipSyncAuditRecord, ...],
    ) -> CheckpointGossipSyncAuditSnapshot:
        last = records[-1] if records else None
        return CheckpointGossipSyncAuditSnapshot(
            schema_version=SCHEMA_VERSION,
            registry_id=self.registry_id,
            source_peer_id=self.source_peer_id,
            records=records,
            record_count=len(records),
            head_record_sha256=last.record_sha256 if last else None,
            local_record_count=last.local_record_count if last else 0,
            local_head_record_sha256=(
                last.local_head_record_sha256 if last else None
            ),
            peer_trust_generation=(last.peer_trust_generation if last else None),
            peer_trust_sha256=(last.peer_trust_sha256 if last else None),
        )


class _CheckpointGossipSyncAuditWriter:
    def __init__(
        self,
        store: CheckpointGossipSyncAuditStore,
        descriptor: int,
    ) -> None:
        self._store = store
        self._descriptor = descriptor

    def replay(
        self,
        peer_trust_ledger: CheckpointPeerTrustLedger,
    ) -> CheckpointGossipSyncAuditSnapshot:
        return self._store._snapshot(
            self._store._read_records(self._descriptor, peer_trust_ledger)
        )

    def append(
        self,
        *,
        peer_trust_ledger: CheckpointPeerTrustLedger,
        registry_snapshot: CheckpointRegistrySnapshot,
        sync_policy_sha256: str,
        event: _SyncEvent,
        range_bundle_sha256: str | None = None,
        first_sequence: int | None = None,
        last_sequence: int | None = None,
        imported_records: int = 0,
        transport_operation: _TransportOperation | None = None,
        transport_attempt: int | None = None,
        stop_reason: _StopReason | None = None,
    ) -> CheckpointGossipSyncAuditRecord:
        records = self._store._read_records(self._descriptor, peer_trust_ledger)
        active = peer_trust_ledger.active_trust
        payload = {
            "schema_version": SCHEMA_VERSION,
            "registry_id": self._store.registry_id,
            "source_peer_id": self._store.source_peer_id,
            "audit_sequence": len(records),
            "previous_record_sha256": (
                records[-1].record_sha256 if records else None
            ),
            "event": event,
            "peer_trust_generation": peer_trust_ledger.active_generation,
            "peer_trust_sha256": active.peer_trust_sha256,
            "peer_trust_ledger_sha256": peer_trust_ledger.ledger_sha256,
            "sync_policy_sha256": sync_policy_sha256,
            "local_record_count": registry_snapshot.record_count,
            "local_head_record_sha256": registry_snapshot.head_record_sha256,
            "range_bundle_sha256": range_bundle_sha256,
            "first_sequence": first_sequence,
            "last_sequence": last_sequence,
            "imported_records": imported_records,
            "transport_operation": transport_operation,
            "transport_attempt": transport_attempt,
            "stop_reason": stop_reason,
        }
        record = CheckpointGossipSyncAuditRecord.model_validate(
            {**payload, "record_sha256": _canonical_sha256(payload)}
        )
        encoded = (record.to_json() + "\n").encode("utf-8")
        CheckpointRegistryStore._append_bytes(
            self._descriptor,
            encoded,
            original_size=os.fstat(self._descriptor).st_size,
        )
        return record


async def run_checkpoint_gossip_sync(
    *,
    descriptor_path: Path,
    registry_store: CheckpointRegistryStore,
    audit_store: CheckpointGossipSyncAuditStore,
    peer_trust_ledger: CheckpointPeerTrustLedger,
    witness_trust: TransparencyWitnessTrust,
    authority_root_ledger: SignedAuthorityRootLedger,
    policy: CheckpointGossipSyncPolicy,
) -> CheckpointGossipSyncResult:
    """Pull exact signed ranges until current, bounded, or safely stopped."""
    ledger = CheckpointPeerTrustLedger.model_validate(
        peer_trust_ledger.model_dump(mode="json")
    )
    policy = CheckpointGossipSyncPolicy.model_validate(policy.model_dump(mode="json"))
    if registry_store.registry_id != audit_store.registry_id:
        raise ValueError("checkpoint gossip sync registry and audit stores differ")
    if ledger.registry_id != registry_store.registry_id:
        raise ValueError("checkpoint gossip sync peer trust uses another registry")
    rounds = 0
    ranges_imported = 0
    records_imported = 0
    retries = 0

    with audit_store.locked() as audit:
        snapshot = registry_store.replay(witness_trust, authority_root_ledger)
        audit_snapshot = audit.replay(ledger)
        _validate_audit_against_registry(audit_snapshot, snapshot)
        if audit_snapshot.local_record_count < snapshot.record_count:
            audit.append(
                peer_trust_ledger=ledger,
                registry_snapshot=snapshot,
                sync_policy_sha256=policy.policy_sha256,
                event="recovered",
            )
            audit_snapshot = audit.replay(ledger)
        if (
            audit_snapshot.peer_trust_generation is not None
            and audit_snapshot.peer_trust_generation < ledger.active_generation
        ):
            audit.append(
                peer_trust_ledger=ledger,
                registry_snapshot=snapshot,
                sync_policy_sha256=policy.policy_sha256,
                event="trust_advanced",
            )

        async def request_with_retry(
            operation: _TransportOperation,
            request: Callable[[], Awaitable[object]],
        ) -> object | None:
            nonlocal retries
            for attempt in range(1, policy.max_attempts_per_request + 1):
                try:
                    return await request()
                except (OSError, RuntimeError, TimeoutError):
                    if attempt >= policy.max_attempts_per_request:
                        return None
                    retries += 1
                    audit.append(
                        peer_trust_ledger=ledger,
                        registry_snapshot=snapshot,
                        sync_policy_sha256=policy.policy_sha256,
                        event="retry",
                        transport_operation=operation,
                        transport_attempt=attempt,
                    )
                    await asyncio.sleep(policy.retry_delays_seconds[attempt - 1])
            return None

        while rounds < policy.max_rounds:
            raw_status = await request_with_retry(
                "status",
                lambda: fetch_checkpoint_gossip_status(
                    descriptor_path=descriptor_path
                ),
            )
            if raw_status is None:
                return _stop_sync(
                    audit,
                    ledger,
                    snapshot,
                    audit_store,
                    policy,
                    reason="retry_exhausted",
                    rounds=rounds,
                    ranges_imported=ranges_imported,
                    records_imported=records_imported,
                    retries=retries,
                )
            status = _GossipStatus.model_validate(raw_status)
            if (
                status.registry_id != registry_store.registry_id
                or status.source_peer_id != audit_store.source_peer_id
            ):
                raise ValueError("checkpoint gossip status endpoint does not match sync")
            candidate = _select_range(status, snapshot.record_count)
            if candidate is None:
                reason: _StopReason = (
                    "range_gap"
                    if any(
                        item.first_sequence > snapshot.record_count
                        for item in status.available_ranges
                    )
                    else "up_to_date"
                )
                return _stop_sync(
                    audit,
                    ledger,
                    snapshot,
                    audit_store,
                    policy,
                    reason=reason,
                    rounds=rounds,
                    ranges_imported=ranges_imported,
                    records_imported=records_imported,
                    retries=retries,
                )
            new_records = candidate.last_sequence - snapshot.record_count + 1
            if records_imported + new_records > policy.max_records:
                return _stop_sync(
                    audit,
                    ledger,
                    snapshot,
                    audit_store,
                    policy,
                    reason="record_budget_exhausted",
                    rounds=rounds,
                    ranges_imported=ranges_imported,
                    records_imported=records_imported,
                    retries=retries,
                )
            rounds += 1
            next_sequence = snapshot.record_count
            bundle_record_count = (
                candidate.last_sequence - candidate.first_sequence + 1
            )
            fetch_request: Callable[[], Awaitable[object]] = partial(
                fetch_signed_checkpoint_range,
                descriptor_path=descriptor_path,
                start_sequence=next_sequence,
                max_records=bundle_record_count,
                peer_trust=ledger,
            )
            bundle_result = await request_with_retry(
                "fetch_range",
                fetch_request,
            )
            if bundle_result is None:
                return _stop_sync(
                    audit,
                    ledger,
                    snapshot,
                    audit_store,
                    policy,
                    reason="retry_exhausted",
                    rounds=rounds,
                    ranges_imported=ranges_imported,
                    records_imported=records_imported,
                    retries=retries,
                )
            bundle = SignedCheckpointRangeBundle.model_validate(bundle_result)
            if bundle.range_bundle_sha256 != candidate.range_bundle_sha256:
                raise ValueError("checkpoint gossip status changed before range fetch")
            resolved_trust = ledger.resolve_peer_trust(
                bundle.statement.peer_trust_sha256
            )
            previous_count = snapshot.record_count
            snapshot = registry_store.import_range_bundle(
                bundle,
                resolved_trust,
                witness_trust,
                authority_root_ledger,
            )
            imported = snapshot.record_count - previous_count
            if imported != new_records or imported < 1:
                raise ValueError("checkpoint gossip range made unexpected progress")
            ranges_imported += 1
            records_imported += imported
            audit.append(
                peer_trust_ledger=ledger,
                registry_snapshot=snapshot,
                sync_policy_sha256=policy.policy_sha256,
                event="imported",
                range_bundle_sha256=bundle.range_bundle_sha256,
                first_sequence=bundle.statement.first_sequence,
                last_sequence=bundle.statement.last_sequence,
                imported_records=imported,
            )

        return _stop_sync(
            audit,
            ledger,
            snapshot,
            audit_store,
            policy,
            reason="round_budget_exhausted",
            rounds=rounds,
            ranges_imported=ranges_imported,
            records_imported=records_imported,
            retries=retries,
        )


def _validate_audit_against_registry(
    audit: CheckpointGossipSyncAuditSnapshot,
    registry: CheckpointRegistrySnapshot,
) -> None:
    if audit.local_record_count > registry.record_count:
        raise ValueError("sync audit is ahead of verified checkpoint registry")
    if audit.local_record_count == 0:
        return
    expected_head = registry.records[audit.local_record_count - 1].record_sha256
    if audit.local_head_record_sha256 != expected_head:
        raise ValueError("sync audit pinned registry history does not match")


def _select_range(status: _GossipStatus, next_sequence: int) -> _AvailableRange | None:
    candidates = tuple(
        item
        for item in status.available_ranges
        if item.first_sequence <= next_sequence <= item.last_sequence
    )
    return max(candidates, key=lambda item: item.first_sequence, default=None)


def _stop_sync(
    audit: _CheckpointGossipSyncAuditWriter,
    ledger: CheckpointPeerTrustLedger,
    snapshot: CheckpointRegistrySnapshot,
    audit_store: CheckpointGossipSyncAuditStore,
    policy: CheckpointGossipSyncPolicy,
    *,
    reason: _StopReason,
    rounds: int,
    ranges_imported: int,
    records_imported: int,
    retries: int,
) -> CheckpointGossipSyncResult:
    record = audit.append(
        peer_trust_ledger=ledger,
        registry_snapshot=snapshot,
        sync_policy_sha256=policy.policy_sha256,
        event="stopped",
        stop_reason=reason,
    )
    return CheckpointGossipSyncResult(
        schema_version=SCHEMA_VERSION,
        registry_id=audit_store.registry_id,
        source_peer_id=audit_store.source_peer_id,
        stop_reason=reason,
        rounds_attempted=rounds,
        ranges_imported=ranges_imported,
        records_imported=records_imported,
        retries=retries,
        local_record_count=snapshot.record_count,
        local_head_record_sha256=snapshot.head_record_sha256,
        peer_trust_generation=ledger.active_generation,
        peer_trust_sha256=ledger.active_trust.peer_trust_sha256,
        sync_policy_sha256=policy.policy_sha256,
        sync_audit_head_sha256=record.record_sha256,
    )

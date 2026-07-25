"""Signed checkpoint range and acknowledgement operations over local gossip."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from benchmarks.agent_cli_checkpoint_registry import (
    CheckpointPeerCursorRecord,
    CheckpointPeerCursorStore,
    CheckpointPeerTrust,
    CheckpointPeerTrustSource,
    SignedCheckpointAcknowledgement,
    SignedCheckpointRangeBundle,
    verify_checkpoint_range_bundle,
)
from benchmarks.agent_cli_gossip_transport import (
    MAX_GOSSIP_RESPONSE_BYTES,
    GossipRequestError,
    send_checkpoint_gossip_request,
)


class CheckpointGossipRequestSender(Protocol):
    async def __call__(
        self,
        *,
        operation: str,
        payload: dict[str, object],
    ) -> dict[str, object]: ...


class _RequestModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid", frozen=True)


class _FetchRangeRequest(_RequestModel):
    start_sequence: int = Field(ge=0)
    max_records: int = Field(ge=1, le=1000)


class _SubmitAcknowledgementRequest(_RequestModel):
    acknowledgement: SignedCheckpointAcknowledgement


def _resolve_peer_trust(
    source: CheckpointPeerTrustSource,
    peer_trust_sha256: str,
) -> CheckpointPeerTrust:
    if isinstance(source, CheckpointPeerTrust):
        if source.peer_trust_sha256 != peer_trust_sha256:
            raise ValueError("checkpoint artifact does not match peer trust")
        return source
    resolved = source.resolve_peer_trust(peer_trust_sha256)
    return CheckpointPeerTrust.model_validate(resolved.model_dump(mode="json"))


async def _send_gossip_request(
    *,
    descriptor_path: Path,
    operation: str,
    payload: dict[str, object],
    request_sender: CheckpointGossipRequestSender | None,
) -> dict[str, object]:
    if request_sender is None:
        return await send_checkpoint_gossip_request(
            descriptor_path=descriptor_path,
            operation=operation,
            payload=payload,
        )
    return await request_sender(operation=operation, payload=payload)


class CheckpointGossipService:
    """Expose pre-signed ranges and durably accept signed peer acknowledgements."""

    def __init__(
        self,
        *,
        registry_id: str,
        source_peer_id: str,
        range_bundles: tuple[SignedCheckpointRangeBundle, ...],
        cursor_store: CheckpointPeerCursorStore,
        peer_trust: CheckpointPeerTrustSource,
    ) -> None:
        if not registry_id or registry_id != registry_id.strip():
            raise ValueError("registry_id must be non-blank without surrounding whitespace")
        if not source_peer_id or source_peer_id != source_peer_id.strip():
            raise ValueError(
                "source_peer_id must be non-blank without surrounding whitespace"
            )
        if cursor_store.registry_id != registry_id:
            raise ValueError("checkpoint gossip cursor store uses another registry")
        normalized = tuple(
            SignedCheckpointRangeBundle.model_validate(bundle.model_dump(mode="json"))
            for bundle in range_bundles
        )
        if not normalized:
            raise ValueError("checkpoint gossip requires at least one signed range bundle")
        first_sequences: set[int] = set()
        for bundle in normalized:
            statement = bundle.statement
            if statement.registry_id != registry_id:
                raise ValueError("checkpoint gossip range uses another registry")
            if statement.source_peer_id != source_peer_id:
                raise ValueError("checkpoint gossip range uses another source peer")
            if statement.first_sequence in first_sequences:
                raise ValueError("checkpoint gossip range starts must be unique")
            first_sequences.add(statement.first_sequence)
            trust = _resolve_peer_trust(peer_trust, statement.peer_trust_sha256)
            verify_checkpoint_range_bundle(bundle, trust)
            encoded_size = len(bundle.to_json().encode("utf-8"))
            if encoded_size > MAX_GOSSIP_RESPONSE_BYTES - 4096:
                raise ValueError("checkpoint gossip range exceeds response limit")
        self.registry_id = registry_id
        self.source_peer_id = source_peer_id
        self._range_bundles = tuple(
            sorted(normalized, key=lambda item: item.statement.first_sequence)
        )
        self._cursor_store = cursor_store
        self._peer_trust = peer_trust

    async def dispatch(
        self,
        operation: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        if operation == "status":
            if payload:
                raise GossipRequestError("invalid_status_payload")
            return {
                "available_ranges": [
                    {
                        "first_sequence": bundle.statement.first_sequence,
                        "last_sequence": bundle.statement.last_sequence,
                        "range_bundle_sha256": bundle.range_bundle_sha256,
                    }
                    for bundle in self._range_bundles
                ],
                "registry_id": self.registry_id,
                "source_peer_id": self.source_peer_id,
            }
        if operation == "fetch_range":
            return self._fetch_range(payload)
        if operation == "submit_acknowledgement":
            return self._submit_acknowledgement(payload)
        raise GossipRequestError("unsupported_operation")

    def _fetch_range(self, payload: dict[str, object]) -> dict[str, object]:
        try:
            request = _FetchRangeRequest.model_validate(payload)
        except ValueError as exc:
            raise GossipRequestError("invalid_range_request") from exc
        bundle = next(
            (
                candidate
                for candidate in self._range_bundles
                if candidate.statement.first_sequence <= request.start_sequence
                <= candidate.statement.last_sequence
                and len(candidate.records) <= request.max_records
            ),
            None,
        )
        if bundle is None:
            raise GossipRequestError("range_unavailable")
        return {"range_bundle": bundle.model_dump(mode="json")}

    def _submit_acknowledgement(
        self,
        payload: dict[str, object],
    ) -> dict[str, object]:
        try:
            request = _SubmitAcknowledgementRequest.model_validate(payload)
            acknowledgement = request.acknowledgement
            if acknowledgement.statement.registry_id != self.registry_id:
                raise ValueError("checkpoint acknowledgement uses another registry")
            if acknowledgement.statement.source_peer_id != self.source_peer_id:
                raise ValueError("checkpoint acknowledgement uses another source peer")
            record = self._cursor_store.append(
                acknowledgement,
                self._peer_trust,
            )
        except (OSError, ValueError) as exc:
            raise GossipRequestError("invalid_acknowledgement") from exc
        return {"cursor_record": record.model_dump(mode="json")}


async def fetch_signed_checkpoint_range(
    *,
    descriptor_path: Path,
    start_sequence: int,
    max_records: int,
    peer_trust: CheckpointPeerTrustSource,
    request_sender: CheckpointGossipRequestSender | None = None,
) -> SignedCheckpointRangeBundle:
    """Fetch and independently verify one already signed range bundle."""
    request = _FetchRangeRequest(
        start_sequence=start_sequence,
        max_records=max_records,
    )
    result = await _send_gossip_request(
        descriptor_path=descriptor_path,
        operation="fetch_range",
        payload=request.model_dump(mode="json"),
        request_sender=request_sender,
    )
    payload = result.get("range_bundle")
    if not isinstance(payload, dict):
        raise RuntimeError("checkpoint gossip response omitted its range bundle")
    bundle = SignedCheckpointRangeBundle.model_validate(payload)
    trust = _resolve_peer_trust(peer_trust, bundle.statement.peer_trust_sha256)
    verify_checkpoint_range_bundle(bundle, trust)
    return bundle


async def submit_signed_checkpoint_acknowledgement(
    *,
    descriptor_path: Path,
    acknowledgement: SignedCheckpointAcknowledgement,
    request_sender: CheckpointGossipRequestSender | None = None,
) -> CheckpointPeerCursorRecord:
    """Submit one signed acknowledgement and validate the returned cursor record."""
    request = _SubmitAcknowledgementRequest(acknowledgement=acknowledgement)
    result = await _send_gossip_request(
        descriptor_path=descriptor_path,
        operation="submit_acknowledgement",
        payload=request.model_dump(mode="json"),
        request_sender=request_sender,
    )
    payload = result.get("cursor_record")
    if not isinstance(payload, dict):
        raise RuntimeError("checkpoint gossip response omitted its cursor record")
    record = CheckpointPeerCursorRecord.model_validate(payload)
    if record.acknowledgement != acknowledgement:
        raise RuntimeError("checkpoint gossip cursor response changed acknowledgement")
    return record


async def fetch_checkpoint_gossip_status(
    *,
    descriptor_path: Path,
    request_sender: CheckpointGossipRequestSender | None = None,
) -> dict[str, object]:
    """Return authenticated online range availability without mutating either peer."""
    return await _send_gossip_request(
        descriptor_path=descriptor_path,
        operation="status",
        payload={},
        request_sender=request_sender,
    )

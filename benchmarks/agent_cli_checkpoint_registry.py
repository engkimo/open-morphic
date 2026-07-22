"""Durable witnessed-checkpoint registry and authenticated peer exchange."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.agent_cli_comparison import SCHEMA_VERSION
from benchmarks.agent_cli_transparency import (
    SignedAuthorityRootLedger,
    TransparencyConsistencyProof,
)
from benchmarks.agent_cli_witness import (
    SignedWitnessCheckpoint,
    TransparencyWitnessTrust,
    detect_witness_checkpoint_conflict,
    verify_witness_checkpoint_bundle,
)

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


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
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def _validate_identifier(identifier: str, *, label: str) -> None:
    if not identifier or identifier != identifier.strip():
        raise ValueError(f"{label} must be non-blank without surrounding whitespace")


def _decode_base64(value: str, *, label: str, length: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be canonical base64") from exc
    if len(decoded) != length or base64.b64encode(decoded).decode() != value:
        raise ValueError(f"{label} must encode exactly {length} bytes")
    return decoded


class CheckpointRegistryRecord(_FrozenModel):
    schema_version: int
    registry_id: str = Field(min_length=1, max_length=200)
    sequence: int = Field(ge=0)
    previous_record_sha256: str | None = Field(
        default=None,
        pattern=_SHA256_PATTERN,
    )
    authority_root_ledger_sha256: str = Field(pattern=_SHA256_PATTERN)
    witness_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    consistency_proof: TransparencyConsistencyProof
    checkpoint: SignedWitnessCheckpoint
    record_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_record(self) -> CheckpointRegistryRecord:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.registry_id, label="registry_id")
        if self.record_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("checkpoint registry record fingerprint does not match")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"record_sha256"})

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class CheckpointRegistrySnapshot(_FrozenModel):
    schema_version: int
    registry_id: str
    records: tuple[CheckpointRegistryRecord, ...]
    record_count: int = Field(ge=0)
    head_record_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    current_tree_size: int | None = Field(default=None, ge=1)
    current_root_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_snapshot(self) -> CheckpointRegistrySnapshot:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.registry_id, label="registry_id")
        if self.record_count != len(self.records):
            raise ValueError("checkpoint snapshot record_count does not match records")
        for sequence, record in enumerate(self.records):
            if record.registry_id != self.registry_id or record.sequence != sequence:
                raise ValueError("checkpoint snapshot record sequence is invalid")
            expected_previous = (
                self.records[sequence - 1].record_sha256 if sequence else None
            )
            if record.previous_record_sha256 != expected_previous:
                raise ValueError("checkpoint snapshot hash chain is invalid")
        last = self.records[-1] if self.records else None
        expected = (
            last.record_sha256 if last else None,
            last.checkpoint.statement.current_tree_size if last else None,
            last.checkpoint.statement.current_root_sha256 if last else None,
        )
        actual = (
            self.head_record_sha256,
            self.current_tree_size,
            self.current_root_sha256,
        )
        if actual != expected:
            raise ValueError("checkpoint snapshot head metadata does not match records")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class CheckpointPeerKeyDeclaration(_FrozenModel):
    peer_id: str = Field(min_length=1, max_length=200)
    key_id: str = Field(min_length=1, max_length=200)
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: str = Field(min_length=1)
    status: Literal["active", "revoked"] = "active"

    @model_validator(mode="after")
    def validate_key(self) -> CheckpointPeerKeyDeclaration:
        _validate_identifier(self.peer_id, label="peer_id")
        _validate_identifier(self.key_id, label="key_id")
        _decode_base64(self.public_key_base64, label="peer public key", length=32)
        return self


class CheckpointPeerTrustDeclaration(_FrozenModel):
    schema_version: int
    registry_id: str = Field(min_length=1, max_length=200)
    keys: tuple[CheckpointPeerKeyDeclaration, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_declaration(self) -> CheckpointPeerTrustDeclaration:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.registry_id, label="registry_id")
        identities = [(key.peer_id, key.key_id) for key in self.keys]
        if len(identities) != len(set(identities)):
            raise ValueError("peer key identities must be unique")
        if len({key.key_id for key in self.keys}) != len(self.keys):
            raise ValueError("peer key_id values must be globally unique")
        return self


class CheckpointPeerKey(_FrozenModel):
    peer_id: str = Field(min_length=1, max_length=200)
    key_id: str = Field(min_length=1, max_length=200)
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: str = Field(min_length=1)
    public_key_sha256: str = Field(pattern=_SHA256_PATTERN)
    status: Literal["active", "revoked"]

    @model_validator(mode="after")
    def validate_key(self) -> CheckpointPeerKey:
        declaration = CheckpointPeerKeyDeclaration(
            peer_id=self.peer_id,
            key_id=self.key_id,
            algorithm=self.algorithm,
            public_key_base64=self.public_key_base64,
            status=self.status,
        )
        decoded = _decode_base64(
            declaration.public_key_base64,
            label="peer public key",
            length=32,
        )
        if self.public_key_sha256 != hashlib.sha256(decoded).hexdigest():
            raise ValueError("peer public key fingerprint does not match key")
        return self


def _peer_key_identity(
    key: CheckpointPeerKey | CheckpointPeerKeyDeclaration,
) -> tuple[str, str]:
    return key.peer_id, key.key_id


class CheckpointPeerTrust(_FrozenModel):
    schema_version: int
    registry_id: str = Field(min_length=1, max_length=200)
    keys: tuple[CheckpointPeerKey, ...] = Field(min_length=1)
    peer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_trust(self) -> CheckpointPeerTrust:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.registry_id, label="registry_id")
        if tuple(sorted(self.keys, key=_peer_key_identity)) != self.keys:
            raise ValueError("peer keys must be sorted")
        if len({key.key_id for key in self.keys}) != len(self.keys):
            raise ValueError("peer key_id values must be globally unique")
        declared_peers = {key.peer_id for key in self.keys}
        active_peers = {key.peer_id for key in self.keys if key.status == "active"}
        missing = sorted(declared_peers - active_peers)
        if missing:
            raise ValueError(f"peer has no active key: {', '.join(missing)}")
        if self.peer_trust_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("peer trust fingerprint does not match declaration")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"peer_trust_sha256"})

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def build_checkpoint_peer_trust(
    declaration: CheckpointPeerTrustDeclaration,
) -> CheckpointPeerTrust:
    """Normalize an authenticated registry-peer key set."""
    keys = tuple(
        sorted(
            (
                CheckpointPeerKey(
                    peer_id=key.peer_id,
                    key_id=key.key_id,
                    algorithm=key.algorithm,
                    public_key_base64=key.public_key_base64,
                    public_key_sha256=hashlib.sha256(
                        _decode_base64(
                            key.public_key_base64,
                            label="peer public key",
                            length=32,
                        )
                    ).hexdigest(),
                    status=key.status,
                )
                for key in declaration.keys
            ),
            key=_peer_key_identity,
        )
    )
    payload = {
        "schema_version": declaration.schema_version,
        "registry_id": declaration.registry_id,
        "keys": [key.model_dump(mode="json") for key in keys],
    }
    return CheckpointPeerTrust(
        **payload,
        peer_trust_sha256=_canonical_sha256(payload),
    )


class CheckpointExchangeStatement(_FrozenModel):
    schema_version: int
    registry_id: str = Field(min_length=1, max_length=200)
    source_peer_id: str = Field(min_length=1, max_length=200)
    peer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    record_sequence: int = Field(ge=0)
    record_sha256: str = Field(pattern=_SHA256_PATTERN)
    witness_checkpoint_sha256: str = Field(pattern=_SHA256_PATTERN)
    log_id: str = Field(min_length=1, max_length=200)
    current_tree_size: int = Field(ge=2)
    current_root_sha256: str = Field(pattern=_SHA256_PATTERN)
    exchange_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_statement(self) -> CheckpointExchangeStatement:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.registry_id, label="registry_id")
        _validate_identifier(self.source_peer_id, label="source_peer_id")
        if self.exchange_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("checkpoint exchange fingerprint does not match statement")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"exchange_sha256"})

    def signing_bytes(self) -> bytes:
        return _canonical_json(self.model_dump(mode="json")).encode()


class CheckpointExchangeSigningRequest(_FrozenModel):
    source_peer_id: str
    eligible_key_ids: tuple[str, ...] = Field(min_length=1)
    statement: CheckpointExchangeStatement
    signing_payload_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_request(self) -> CheckpointExchangeSigningRequest:
        if tuple(sorted(set(self.eligible_key_ids))) != self.eligible_key_ids:
            raise ValueError("eligible peer key IDs must be sorted and unique")
        expected = self.statement.signing_bytes()
        decoded = _decode_base64(
            self.signing_payload_base64,
            label="checkpoint exchange signing payload",
            length=len(expected),
        )
        if decoded != expected:
            raise ValueError("checkpoint exchange payload does not match statement")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class SignedCheckpointExchangePacket(_FrozenModel):
    schema_version: int
    statement: CheckpointExchangeStatement
    record: CheckpointRegistryRecord
    key_id: str = Field(min_length=1, max_length=200)
    signature_base64: str = Field(min_length=1)
    packet_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_packet(self) -> SignedCheckpointExchangePacket:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.key_id, label="key_id")
        _decode_base64(
            self.signature_base64,
            label="checkpoint exchange signature",
            length=64,
        )
        if self.packet_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("checkpoint exchange packet fingerprint does not match")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"packet_sha256"})

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _exchange_statement(
    record: CheckpointRegistryRecord,
    trust: CheckpointPeerTrust,
    *,
    source_peer_id: str,
) -> CheckpointExchangeStatement:
    record = CheckpointRegistryRecord.model_validate(record.model_dump(mode="json"))
    trust = CheckpointPeerTrust.model_validate(trust.model_dump(mode="json"))
    if record.registry_id != trust.registry_id:
        raise ValueError("checkpoint record does not match peer trust registry")
    active = [key for key in trust.keys if key.peer_id == source_peer_id and key.status == "active"]
    if not active:
        raise ValueError("source peer has no active trusted key")
    current = record.checkpoint.statement
    payload = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": record.registry_id,
        "source_peer_id": source_peer_id,
        "peer_trust_sha256": trust.peer_trust_sha256,
        "record_sequence": record.sequence,
        "record_sha256": record.record_sha256,
        "witness_checkpoint_sha256": record.checkpoint.witness_checkpoint_sha256,
        "log_id": current.log_id,
        "current_tree_size": current.current_tree_size,
        "current_root_sha256": current.current_root_sha256,
    }
    return CheckpointExchangeStatement(
        **payload,
        exchange_sha256=_canonical_sha256(payload),
    )


def build_checkpoint_exchange_request(
    record: CheckpointRegistryRecord,
    trust: CheckpointPeerTrust,
    *,
    source_peer_id: str,
) -> CheckpointExchangeSigningRequest:
    """Create a private-key-free request for one exact registry record."""
    statement = _exchange_statement(record, trust, source_peer_id=source_peer_id)
    eligible = tuple(
        sorted(
            key.key_id
            for key in trust.keys
            if key.peer_id == source_peer_id and key.status == "active"
        )
    )
    return CheckpointExchangeSigningRequest(
        source_peer_id=source_peer_id,
        eligible_key_ids=eligible,
        statement=statement,
        signing_payload_base64=base64.b64encode(statement.signing_bytes()).decode(),
    )


def build_signed_checkpoint_exchange_packet(
    request: CheckpointExchangeSigningRequest,
    record: CheckpointRegistryRecord,
    *,
    key_id: str,
    signature_base64: str,
    peer_trust: CheckpointPeerTrust,
) -> SignedCheckpointExchangePacket:
    """Bind a detached peer signature to the exact exported record."""
    expected = build_checkpoint_exchange_request(
        record,
        peer_trust,
        source_peer_id=request.source_peer_id,
    )
    if request != expected:
        raise ValueError("checkpoint exchange request does not match record")
    if key_id not in request.eligible_key_ids:
        raise ValueError("checkpoint exchange signature does not use an active trusted key")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "statement": request.statement.model_dump(mode="json"),
        "record": record.model_dump(mode="json"),
        "key_id": key_id,
        "signature_base64": signature_base64,
    }
    packet = SignedCheckpointExchangePacket(
        **payload,
        packet_sha256=_canonical_sha256(payload),
    )
    verify_checkpoint_exchange_packet(packet, peer_trust)
    return packet


def verify_checkpoint_exchange_packet(
    packet: SignedCheckpointExchangePacket,
    trust: CheckpointPeerTrust,
) -> CheckpointRegistryRecord:
    """Authenticate a peer packet and its exact self-fingerprinted record."""
    packet = SignedCheckpointExchangePacket.model_validate(packet.model_dump(mode="json"))
    trust = CheckpointPeerTrust.model_validate(trust.model_dump(mode="json"))
    key = next(
        (
            candidate
            for candidate in trust.keys
            if candidate.peer_id == packet.statement.source_peer_id
            and candidate.key_id == packet.key_id
            and candidate.status == "active"
        ),
        None,
    )
    if key is None:
        raise ValueError("checkpoint exchange signature does not use an active trusted key")
    if packet.statement.peer_trust_sha256 != trust.peer_trust_sha256:
        raise ValueError("checkpoint exchange does not match peer trust")
    expected = _exchange_statement(
        packet.record,
        trust,
        source_peer_id=packet.statement.source_peer_id,
    )
    if packet.statement != expected:
        raise ValueError("checkpoint exchange statement does not match record")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode_base64(key.public_key_base64, label="peer public key", length=32)
        ).verify(
            _decode_base64(
                packet.signature_base64,
                label="checkpoint exchange signature",
                length=64,
            ),
            packet.statement.signing_bytes(),
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("checkpoint exchange signature is invalid") from exc
    return packet.record


class CheckpointRangeStatement(_FrozenModel):
    schema_version: int
    registry_id: str = Field(min_length=1, max_length=200)
    source_peer_id: str = Field(min_length=1, max_length=200)
    peer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    first_sequence: int = Field(ge=0)
    last_sequence: int = Field(ge=0)
    base_previous_record_sha256: str | None = Field(
        default=None,
        pattern=_SHA256_PATTERN,
    )
    first_record_sha256: str = Field(pattern=_SHA256_PATTERN)
    last_record_sha256: str = Field(pattern=_SHA256_PATTERN)
    records_sha256: str = Field(pattern=_SHA256_PATTERN)
    range_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_statement(self) -> CheckpointRangeStatement:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.registry_id, label="registry_id")
        _validate_identifier(self.source_peer_id, label="source_peer_id")
        if self.first_sequence > self.last_sequence:
            raise ValueError("checkpoint range sequence is inverted")
        if self.range_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("checkpoint range fingerprint does not match statement")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"range_sha256"})

    def signing_bytes(self) -> bytes:
        return _canonical_json(self.model_dump(mode="json")).encode()


class CheckpointRangeSigningRequest(_FrozenModel):
    source_peer_id: str
    eligible_key_ids: tuple[str, ...] = Field(min_length=1)
    statement: CheckpointRangeStatement
    signing_payload_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_request(self) -> CheckpointRangeSigningRequest:
        if self.source_peer_id != self.statement.source_peer_id:
            raise ValueError("checkpoint range request source peer does not match statement")
        if tuple(sorted(set(self.eligible_key_ids))) != self.eligible_key_ids:
            raise ValueError("eligible range key IDs must be sorted and unique")
        expected = self.statement.signing_bytes()
        decoded = _decode_base64(
            self.signing_payload_base64,
            label="checkpoint range signing payload",
            length=len(expected),
        )
        if decoded != expected:
            raise ValueError("checkpoint range payload does not match statement")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class SignedCheckpointRangeBundle(_FrozenModel):
    schema_version: int
    statement: CheckpointRangeStatement
    records: tuple[CheckpointRegistryRecord, ...] = Field(min_length=1)
    key_id: str = Field(min_length=1, max_length=200)
    signature_base64: str = Field(min_length=1)
    range_bundle_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_bundle(self) -> SignedCheckpointRangeBundle:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.key_id, label="key_id")
        _decode_base64(
            self.signature_base64,
            label="checkpoint range signature",
            length=64,
        )
        if self.range_bundle_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("checkpoint range bundle fingerprint does not match")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"range_bundle_sha256"})

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _validate_range_records(
    records: tuple[CheckpointRegistryRecord, ...],
) -> tuple[CheckpointRegistryRecord, ...]:
    if not records:
        raise ValueError("checkpoint range requires at least one record")
    normalized = tuple(
        CheckpointRegistryRecord.model_validate(record.model_dump(mode="json"))
        for record in records
    )
    registry_id = normalized[0].registry_id
    for index, record in enumerate(normalized):
        if record.registry_id != registry_id:
            raise ValueError("checkpoint range records use different registries")
        if record.sequence != normalized[0].sequence + index:
            raise ValueError("checkpoint range sequence is not contiguous")
        if index and record.previous_record_sha256 != normalized[index - 1].record_sha256:
            raise ValueError("checkpoint range hash chain is invalid")
    return normalized


def _checkpoint_range_statement(
    records: tuple[CheckpointRegistryRecord, ...],
    trust: CheckpointPeerTrust,
    *,
    source_peer_id: str,
) -> CheckpointRangeStatement:
    records = _validate_range_records(records)
    trust = CheckpointPeerTrust.model_validate(trust.model_dump(mode="json"))
    if records[0].registry_id != trust.registry_id:
        raise ValueError("checkpoint range does not match peer trust registry")
    active = tuple(
        key
        for key in trust.keys
        if key.peer_id == source_peer_id and key.status == "active"
    )
    if not active:
        raise ValueError("source peer has no active trusted key")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": records[0].registry_id,
        "source_peer_id": source_peer_id,
        "peer_trust_sha256": trust.peer_trust_sha256,
        "first_sequence": records[0].sequence,
        "last_sequence": records[-1].sequence,
        "base_previous_record_sha256": records[0].previous_record_sha256,
        "first_record_sha256": records[0].record_sha256,
        "last_record_sha256": records[-1].record_sha256,
        "records_sha256": _canonical_sha256(
            [record.record_sha256 for record in records]
        ),
    }
    return CheckpointRangeStatement(
        **payload,
        range_sha256=_canonical_sha256(payload),
    )


def build_checkpoint_range_request(
    records: tuple[CheckpointRegistryRecord, ...],
    trust: CheckpointPeerTrust,
    *,
    source_peer_id: str,
) -> CheckpointRangeSigningRequest:
    """Create one detached signing request for a contiguous record range."""
    statement = _checkpoint_range_statement(
        records,
        trust,
        source_peer_id=source_peer_id,
    )
    eligible = tuple(
        sorted(
            key.key_id
            for key in trust.keys
            if key.peer_id == source_peer_id and key.status == "active"
        )
    )
    return CheckpointRangeSigningRequest(
        source_peer_id=source_peer_id,
        eligible_key_ids=eligible,
        statement=statement,
        signing_payload_base64=base64.b64encode(statement.signing_bytes()).decode(),
    )


def build_signed_checkpoint_range_bundle(
    request: CheckpointRangeSigningRequest,
    records: tuple[CheckpointRegistryRecord, ...],
    *,
    key_id: str,
    signature_base64: str,
    peer_trust: CheckpointPeerTrust,
) -> SignedCheckpointRangeBundle:
    """Bind one peer signature to an exact contiguous record range."""
    expected = build_checkpoint_range_request(
        records,
        peer_trust,
        source_peer_id=request.source_peer_id,
    )
    if request != expected:
        raise ValueError("checkpoint range request does not match records")
    if key_id not in request.eligible_key_ids:
        raise ValueError("checkpoint range signature does not use an active trusted key")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "statement": request.statement.model_dump(mode="json"),
        "records": [record.model_dump(mode="json") for record in records],
        "key_id": key_id,
        "signature_base64": signature_base64,
    }
    bundle = SignedCheckpointRangeBundle(
        **payload,
        range_bundle_sha256=_canonical_sha256(payload),
    )
    verify_checkpoint_range_bundle(bundle, peer_trust)
    return bundle


def verify_checkpoint_range_bundle(
    bundle: SignedCheckpointRangeBundle,
    trust: CheckpointPeerTrust,
) -> tuple[CheckpointRegistryRecord, ...]:
    """Authenticate a peer and every exact record in one contiguous range."""
    bundle = SignedCheckpointRangeBundle.model_validate(bundle.model_dump(mode="json"))
    trust = CheckpointPeerTrust.model_validate(trust.model_dump(mode="json"))
    key = next(
        (
            candidate
            for candidate in trust.keys
            if candidate.peer_id == bundle.statement.source_peer_id
            and candidate.key_id == bundle.key_id
            and candidate.status == "active"
        ),
        None,
    )
    if key is None:
        raise ValueError("checkpoint range signature does not use an active trusted key")
    if bundle.statement.peer_trust_sha256 != trust.peer_trust_sha256:
        raise ValueError("checkpoint range does not match peer trust")
    expected = _checkpoint_range_statement(
        bundle.records,
        trust,
        source_peer_id=bundle.statement.source_peer_id,
    )
    if bundle.statement != expected:
        raise ValueError("checkpoint range statement does not match records")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode_base64(key.public_key_base64, label="peer public key", length=32)
        ).verify(
            _decode_base64(
                bundle.signature_base64,
                label="checkpoint range signature",
                length=64,
            ),
            bundle.statement.signing_bytes(),
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("checkpoint range signature is invalid") from exc
    return bundle.records


class CheckpointAcknowledgementStatement(_FrozenModel):
    schema_version: int
    registry_id: str = Field(min_length=1, max_length=200)
    source_peer_id: str = Field(min_length=1, max_length=200)
    acknowledging_peer_id: str = Field(min_length=1, max_length=200)
    peer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    range_bundle_sha256: str = Field(pattern=_SHA256_PATTERN)
    first_sequence: int = Field(ge=0)
    acknowledged_record_sequence: int = Field(ge=0)
    acknowledged_record_sha256: str = Field(pattern=_SHA256_PATTERN)
    acknowledged_tree_size: int = Field(ge=2)
    acknowledged_root_sha256: str = Field(pattern=_SHA256_PATTERN)
    acknowledgement_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_statement(self) -> CheckpointAcknowledgementStatement:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.registry_id, label="registry_id")
        _validate_identifier(self.source_peer_id, label="source_peer_id")
        _validate_identifier(
            self.acknowledging_peer_id,
            label="acknowledging_peer_id",
        )
        if self.source_peer_id == self.acknowledging_peer_id:
            raise ValueError("checkpoint acknowledgement requires a distinct peer")
        if self.first_sequence > self.acknowledged_record_sequence:
            raise ValueError("checkpoint acknowledgement range is inverted")
        if self.acknowledgement_sha256 != _canonical_sha256(
            self._binding_payload()
        ):
            raise ValueError("checkpoint acknowledgement fingerprint does not match")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"acknowledgement_sha256"})

    def signing_bytes(self) -> bytes:
        return _canonical_json(self.model_dump(mode="json")).encode()


class CheckpointAcknowledgementSigningRequest(_FrozenModel):
    acknowledging_peer_id: str
    eligible_key_ids: tuple[str, ...] = Field(min_length=1)
    statement: CheckpointAcknowledgementStatement
    signing_payload_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_request(self) -> CheckpointAcknowledgementSigningRequest:
        if self.acknowledging_peer_id != self.statement.acknowledging_peer_id:
            raise ValueError(
                "checkpoint acknowledgement request peer does not match statement"
            )
        if tuple(sorted(set(self.eligible_key_ids))) != self.eligible_key_ids:
            raise ValueError("eligible acknowledgement key IDs must be sorted and unique")
        expected = self.statement.signing_bytes()
        decoded = _decode_base64(
            self.signing_payload_base64,
            label="checkpoint acknowledgement signing payload",
            length=len(expected),
        )
        if decoded != expected:
            raise ValueError("checkpoint acknowledgement payload does not match statement")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class SignedCheckpointAcknowledgement(_FrozenModel):
    schema_version: int
    statement: CheckpointAcknowledgementStatement
    key_id: str = Field(min_length=1, max_length=200)
    signature_base64: str = Field(min_length=1)
    signed_acknowledgement_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_acknowledgement(self) -> SignedCheckpointAcknowledgement:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.key_id, label="key_id")
        _decode_base64(
            self.signature_base64,
            label="checkpoint acknowledgement signature",
            length=64,
        )
        if self.signed_acknowledgement_sha256 != _canonical_sha256(
            self._binding_payload()
        ):
            raise ValueError("signed checkpoint acknowledgement fingerprint does not match")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(
            mode="json",
            exclude={"signed_acknowledgement_sha256"},
        )

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def build_checkpoint_acknowledgement_request(
    bundle: SignedCheckpointRangeBundle,
    snapshot: CheckpointRegistrySnapshot,
    trust: CheckpointPeerTrust,
    *,
    acknowledging_peer_id: str,
) -> CheckpointAcknowledgementSigningRequest:
    """Confirm that an authenticated range is the receiver's exact current head."""
    records = verify_checkpoint_range_bundle(bundle, trust)
    snapshot = CheckpointRegistrySnapshot.model_validate(
        snapshot.model_dump(mode="json")
    )
    if snapshot.registry_id != bundle.statement.registry_id:
        raise ValueError("checkpoint acknowledgement snapshot uses another registry")
    if snapshot.head_record_sha256 != records[-1].record_sha256:
        raise ValueError("checkpoint acknowledgement range is not the registry head")
    for record in records:
        if record.sequence >= len(snapshot.records) or snapshot.records[record.sequence] != record:
            raise ValueError("checkpoint acknowledgement range is not applied exactly")
    eligible = tuple(
        sorted(
            key.key_id
            for key in trust.keys
            if key.peer_id == acknowledging_peer_id and key.status == "active"
        )
    )
    if not eligible:
        raise ValueError("acknowledging peer has no active trusted key")
    last = records[-1]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": bundle.statement.registry_id,
        "source_peer_id": bundle.statement.source_peer_id,
        "acknowledging_peer_id": acknowledging_peer_id,
        "peer_trust_sha256": trust.peer_trust_sha256,
        "range_bundle_sha256": bundle.range_bundle_sha256,
        "first_sequence": records[0].sequence,
        "acknowledged_record_sequence": last.sequence,
        "acknowledged_record_sha256": last.record_sha256,
        "acknowledged_tree_size": last.checkpoint.statement.current_tree_size,
        "acknowledged_root_sha256": last.checkpoint.statement.current_root_sha256,
    }
    statement = CheckpointAcknowledgementStatement(
        **payload,
        acknowledgement_sha256=_canonical_sha256(payload),
    )
    return CheckpointAcknowledgementSigningRequest(
        acknowledging_peer_id=acknowledging_peer_id,
        eligible_key_ids=eligible,
        statement=statement,
        signing_payload_base64=base64.b64encode(statement.signing_bytes()).decode(),
    )


def build_signed_checkpoint_acknowledgement(
    request: CheckpointAcknowledgementSigningRequest,
    *,
    key_id: str,
    signature_base64: str,
    peer_trust: CheckpointPeerTrust,
) -> SignedCheckpointAcknowledgement:
    """Attach and verify one receiver signature over an applied range head."""
    request = CheckpointAcknowledgementSigningRequest.model_validate(
        request.model_dump(mode="json")
    )
    peer_trust = CheckpointPeerTrust.model_validate(
        peer_trust.model_dump(mode="json")
    )
    if request.statement.peer_trust_sha256 != peer_trust.peer_trust_sha256:
        raise ValueError("checkpoint acknowledgement does not match peer trust")
    active = {
        key.key_id
        for key in peer_trust.keys
        if key.peer_id == request.acknowledging_peer_id and key.status == "active"
    }
    if request.eligible_key_ids != tuple(sorted(active)) or key_id not in active:
        raise ValueError(
            "checkpoint acknowledgement signature does not use an active trusted key"
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "statement": request.statement.model_dump(mode="json"),
        "key_id": key_id,
        "signature_base64": signature_base64,
    }
    acknowledgement = SignedCheckpointAcknowledgement(
        **payload,
        signed_acknowledgement_sha256=_canonical_sha256(payload),
    )
    verify_checkpoint_acknowledgement(acknowledgement, peer_trust)
    return acknowledgement


def verify_checkpoint_acknowledgement(
    acknowledgement: SignedCheckpointAcknowledgement,
    trust: CheckpointPeerTrust,
) -> CheckpointAcknowledgementStatement:
    """Authenticate a receiver's exact range/head acknowledgement."""
    acknowledgement = SignedCheckpointAcknowledgement.model_validate(
        acknowledgement.model_dump(mode="json")
    )
    trust = CheckpointPeerTrust.model_validate(trust.model_dump(mode="json"))
    statement = acknowledgement.statement
    key = next(
        (
            candidate
            for candidate in trust.keys
            if candidate.peer_id == statement.acknowledging_peer_id
            and candidate.key_id == acknowledgement.key_id
            and candidate.status == "active"
        ),
        None,
    )
    if key is None:
        raise ValueError(
            "checkpoint acknowledgement signature does not use an active trusted key"
        )
    if statement.peer_trust_sha256 != trust.peer_trust_sha256:
        raise ValueError("checkpoint acknowledgement does not match peer trust")
    if statement.registry_id != trust.registry_id:
        raise ValueError("checkpoint acknowledgement does not match trust registry")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode_base64(key.public_key_base64, label="peer public key", length=32)
        ).verify(
            _decode_base64(
                acknowledgement.signature_base64,
                label="checkpoint acknowledgement signature",
                length=64,
            ),
            statement.signing_bytes(),
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("checkpoint acknowledgement signature is invalid") from exc
    return statement


def _build_registry_record(
    *,
    registry_id: str,
    sequence: int,
    previous_record_sha256: str | None,
    proof: TransparencyConsistencyProof,
    checkpoint: SignedWitnessCheckpoint,
    witness_trust: TransparencyWitnessTrust,
    ledger: SignedAuthorityRootLedger,
) -> CheckpointRegistryRecord:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": registry_id,
        "sequence": sequence,
        "previous_record_sha256": previous_record_sha256,
        "authority_root_ledger_sha256": ledger.statement.ledger_sha256,
        "witness_trust_sha256": witness_trust.witness_trust_sha256,
        "consistency_proof": proof.model_dump(mode="json"),
        "checkpoint": checkpoint.model_dump(mode="json"),
    }
    return CheckpointRegistryRecord(
        **payload,
        record_sha256=_canonical_sha256(payload),
    )


def _validate_record_bindings(
    record: CheckpointRegistryRecord,
    witness_trust: TransparencyWitnessTrust,
    ledger: SignedAuthorityRootLedger,
) -> None:
    if record.authority_root_ledger_sha256 != ledger.statement.ledger_sha256:
        raise ValueError("checkpoint registry record uses a different root ledger")
    if record.witness_trust_sha256 != witness_trust.witness_trust_sha256:
        raise ValueError("checkpoint registry record uses different witness trust")
    verify_witness_checkpoint_bundle(
        witness_trust,
        record.consistency_proof,
        ledger,
        record.checkpoint,
    )


def _validate_registry_pair(
    previous: CheckpointRegistryRecord,
    current: CheckpointRegistryRecord,
) -> None:
    detect_witness_checkpoint_conflict(previous.checkpoint, current.checkpoint)
    old_current = previous.checkpoint.statement
    new_previous = current.consistency_proof.previous_tree_head.statement
    if (
        new_previous.tree_size,
        new_previous.root_sha256,
        new_previous.tree_head_sha256,
    ) != (
        old_current.current_tree_size,
        old_current.current_root_sha256,
        old_current.current_tree_head_sha256,
    ):
        raise ValueError("checkpoint registry consistency chain is invalid")


class CheckpointRegistryStore:
    """Locked, append-only JSONL storage for witnessed checkpoints."""

    def __init__(self, path: str | Path, *, registry_id: str) -> None:
        self.path = Path(path)
        _validate_identifier(registry_id, label="registry_id")
        self.registry_id = registry_id

    def _open_for_append(self) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            self.path,
            os.O_CREAT
            | os.O_RDWR
            | os.O_APPEND
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise ValueError("checkpoint registry must be a regular file")
        os.fchmod(descriptor, 0o600)
        return descriptor

    def _open_for_replay(self) -> int | None:
        try:
            descriptor = os.open(
                self.path,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise ValueError("checkpoint registry must be a regular file")
        return descriptor

    def _read_records(
        self,
        descriptor: int,
        witness_trust: TransparencyWitnessTrust,
        ledger: SignedAuthorityRootLedger,
    ) -> tuple[CheckpointRegistryRecord, ...]:
        size = os.fstat(descriptor).st_size
        raw = os.pread(descriptor, size, 0)
        if not raw:
            return ()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("checkpoint registry must be UTF-8 JSONL") from exc
        if not text.endswith("\n"):
            raise ValueError("checkpoint registry has a truncated final record")
        records: list[CheckpointRegistryRecord] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            try:
                record = CheckpointRegistryRecord.model_validate_json(line)
            except ValueError as exc:
                raise ValueError(
                    f"invalid checkpoint registry record at line {line_number}: {exc}"
                ) from exc
            if record.registry_id != self.registry_id:
                raise ValueError("checkpoint registry_id does not match store")
            if record.sequence != len(records):
                raise ValueError("checkpoint registry sequence is not contiguous")
            expected_previous = records[-1].record_sha256 if records else None
            if record.previous_record_sha256 != expected_previous:
                raise ValueError("checkpoint registry hash chain is invalid")
            _validate_record_bindings(record, witness_trust, ledger)
            if records:
                _validate_registry_pair(records[-1], record)
            records.append(record)
        return tuple(records)

    @staticmethod
    def _append_bytes(descriptor: int, encoded: bytes, *, original_size: int) -> None:
        position = 0
        try:
            while position < len(encoded):
                written = os.write(descriptor, encoded[position:])
                if written <= 0:
                    raise OSError("checkpoint registry append made no progress")
                position += written
            os.fsync(descriptor)
        except BaseException:
            os.ftruncate(descriptor, original_size)
            os.fsync(descriptor)
            raise

    def _snapshot(
        self,
        records: tuple[CheckpointRegistryRecord, ...],
    ) -> CheckpointRegistrySnapshot:
        last = records[-1] if records else None
        return CheckpointRegistrySnapshot(
            schema_version=SCHEMA_VERSION,
            registry_id=self.registry_id,
            records=records,
            record_count=len(records),
            head_record_sha256=last.record_sha256 if last else None,
            current_tree_size=(
                last.checkpoint.statement.current_tree_size if last else None
            ),
            current_root_sha256=(
                last.checkpoint.statement.current_root_sha256 if last else None
            ),
        )

    def replay(
        self,
        witness_trust: TransparencyWitnessTrust,
        ledger: SignedAuthorityRootLedger,
    ) -> CheckpointRegistrySnapshot:
        """Replay and fully verify every durable record."""
        descriptor = self._open_for_replay()
        if descriptor is None:
            return self._snapshot(())
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH)
            records = self._read_records(descriptor, witness_trust, ledger)
            return self._snapshot(records)
        finally:
            os.close(descriptor)

    def append(
        self,
        proof: TransparencyConsistencyProof,
        checkpoint: SignedWitnessCheckpoint,
        witness_trust: TransparencyWitnessTrust,
        ledger: SignedAuthorityRootLedger,
        *,
        expected_record: CheckpointRegistryRecord | None = None,
    ) -> CheckpointRegistryRecord:
        """Verify and durably append one new checkpoint under an exclusive lock."""
        descriptor = self._open_for_append()
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            records = self._read_records(descriptor, witness_trust, ledger)
            verify_witness_checkpoint_bundle(witness_trust, proof, ledger, checkpoint)
            if records:
                last = records[-1]
                if (
                    checkpoint.witness_checkpoint_sha256
                    == last.checkpoint.witness_checkpoint_sha256
                    and proof.consistency_proof_sha256
                    == last.consistency_proof.consistency_proof_sha256
                ):
                    if expected_record is not None and expected_record != last:
                        raise ValueError("peer checkpoint record does not match local registry")
                    return last
                detect_witness_checkpoint_conflict(last.checkpoint, checkpoint)
                last_current = last.checkpoint.statement
                incoming_previous = proof.previous_tree_head.statement
                if incoming_previous.tree_size < last_current.current_tree_size:
                    raise ValueError("stale checkpoint cannot be appended")
                if (
                    incoming_previous.tree_size,
                    incoming_previous.root_sha256,
                    incoming_previous.tree_head_sha256,
                ) != (
                    last_current.current_tree_size,
                    last_current.current_root_sha256,
                    last_current.current_tree_head_sha256,
                ):
                    raise ValueError("checkpoint does not extend the registry head")
            record = _build_registry_record(
                registry_id=self.registry_id,
                sequence=len(records),
                previous_record_sha256=(records[-1].record_sha256 if records else None),
                proof=proof,
                checkpoint=checkpoint,
                witness_trust=witness_trust,
                ledger=ledger,
            )
            if expected_record is not None:
                expected_record = CheckpointRegistryRecord.model_validate(
                    expected_record.model_dump(mode="json")
                )
                if expected_record != record:
                    raise ValueError("peer checkpoint record does not match local registry")
            encoded = (record.to_json() + "\n").encode()
            self._append_bytes(
                descriptor,
                encoded,
                original_size=os.fstat(descriptor).st_size,
            )
            return record
        finally:
            os.close(descriptor)

    def import_packet(
        self,
        packet: SignedCheckpointExchangePacket,
        peer_trust: CheckpointPeerTrust,
        witness_trust: TransparencyWitnessTrust,
        ledger: SignedAuthorityRootLedger,
    ) -> CheckpointRegistryRecord:
        """Authenticate, verify, and atomically import one exact peer record."""
        record = verify_checkpoint_exchange_packet(packet, peer_trust)
        if peer_trust.registry_id != self.registry_id:
            raise ValueError("peer trust registry_id does not match store")
        return self.append(
            record.consistency_proof,
            record.checkpoint,
            witness_trust,
            ledger,
            expected_record=record,
        )

    def import_range_bundle(
        self,
        bundle: SignedCheckpointRangeBundle,
        peer_trust: CheckpointPeerTrust,
        witness_trust: TransparencyWitnessTrust,
        ledger: SignedAuthorityRootLedger,
    ) -> CheckpointRegistrySnapshot:
        """Atomically append the missing suffix of one authenticated range."""
        incoming = verify_checkpoint_range_bundle(bundle, peer_trust)
        if peer_trust.registry_id != self.registry_id:
            raise ValueError("peer trust registry_id does not match store")
        for index, record in enumerate(incoming):
            _validate_record_bindings(record, witness_trust, ledger)
            if index:
                _validate_registry_pair(incoming[index - 1], record)

        descriptor = self._open_for_append()
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            existing = self._read_records(descriptor, witness_trust, ledger)
            first_sequence = incoming[0].sequence
            if first_sequence > len(existing):
                raise ValueError("checkpoint range would create a registry gap")

            overlap_end = min(len(existing), incoming[-1].sequence + 1)
            for sequence in range(first_sequence, overlap_end):
                received = incoming[sequence - first_sequence]
                if existing[sequence] != received:
                    raise ValueError("conflicting range overlap detected")

            suffix_offset = max(0, len(existing) - first_sequence)
            suffix = incoming[suffix_offset:]
            if not suffix:
                return self._snapshot(existing)
            if suffix[0].sequence != len(existing):
                raise ValueError("checkpoint range would create a registry gap")
            expected_previous = existing[-1].record_sha256 if existing else None
            if suffix[0].previous_record_sha256 != expected_previous:
                raise ValueError("checkpoint range does not extend the registry head")
            if existing:
                _validate_registry_pair(existing[-1], suffix[0])

            encoded = "".join(record.to_json() + "\n" for record in suffix).encode()
            original_size = os.fstat(descriptor).st_size
            self._append_bytes(
                descriptor,
                encoded,
                original_size=original_size,
            )
            return self._snapshot(existing + suffix)
        finally:
            os.close(descriptor)


class CheckpointPeerCursorRecord(_FrozenModel):
    schema_version: int
    registry_id: str = Field(min_length=1, max_length=200)
    cursor_sequence: int = Field(ge=0)
    previous_cursor_record_sha256: str | None = Field(
        default=None,
        pattern=_SHA256_PATTERN,
    )
    acknowledgement: SignedCheckpointAcknowledgement
    cursor_record_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_record(self) -> CheckpointPeerCursorRecord:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.registry_id, label="registry_id")
        if self.cursor_record_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("peer cursor record fingerprint does not match")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"cursor_record_sha256"})

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class CheckpointPeerCursorPosition(_FrozenModel):
    source_peer_id: str
    acknowledging_peer_id: str
    acknowledged_record_sequence: int = Field(ge=0)
    acknowledged_record_sha256: str = Field(pattern=_SHA256_PATTERN)
    range_bundle_sha256: str = Field(pattern=_SHA256_PATTERN)
    signed_acknowledgement_sha256: str = Field(pattern=_SHA256_PATTERN)


class CheckpointPeerCursorSnapshot(_FrozenModel):
    schema_version: int
    registry_id: str
    cursors: tuple[CheckpointPeerCursorRecord, ...]
    cursor_count: int = Field(ge=0)
    head_cursor_record_sha256: str | None = Field(
        default=None,
        pattern=_SHA256_PATTERN,
    )
    positions: tuple[CheckpointPeerCursorPosition, ...]

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _cursor_pair(
    statement: CheckpointAcknowledgementStatement,
) -> tuple[str, str]:
    return statement.source_peer_id, statement.acknowledging_peer_id


def _cursor_position(
    acknowledgement: SignedCheckpointAcknowledgement,
) -> CheckpointPeerCursorPosition:
    statement = acknowledgement.statement
    return CheckpointPeerCursorPosition(
        source_peer_id=statement.source_peer_id,
        acknowledging_peer_id=statement.acknowledging_peer_id,
        acknowledged_record_sequence=statement.acknowledged_record_sequence,
        acknowledged_record_sha256=statement.acknowledged_record_sha256,
        range_bundle_sha256=statement.range_bundle_sha256,
        signed_acknowledgement_sha256=(
            acknowledgement.signed_acknowledgement_sha256
        ),
    )


def _validate_cursor_advance(
    current: CheckpointPeerCursorPosition | None,
    acknowledgement: SignedCheckpointAcknowledgement,
) -> None:
    if current is None:
        return
    statement = acknowledgement.statement
    if statement.acknowledged_record_sequence < current.acknowledged_record_sequence:
        raise ValueError("peer cursor regression is not allowed")
    if statement.acknowledged_record_sequence == current.acknowledged_record_sequence:
        if statement.acknowledged_record_sha256 != current.acknowledged_record_sha256:
            raise ValueError("conflicting peer cursor acknowledgement detected")
        raise ValueError("duplicate peer cursor acknowledgement record")


class CheckpointPeerCursorStore:
    """Append-only acknowledgement ledger with monotonic per-peer cursors."""

    def __init__(self, path: str | Path, *, registry_id: str) -> None:
        self.path = Path(path)
        _validate_identifier(registry_id, label="registry_id")
        self.registry_id = registry_id

    def _open_for_append(self) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            self.path,
            os.O_CREAT
            | os.O_RDWR
            | os.O_APPEND
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise ValueError("peer cursor ledger must be a regular file")
        os.fchmod(descriptor, 0o600)
        return descriptor

    def _open_for_replay(self) -> int | None:
        try:
            descriptor = os.open(
                self.path,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise ValueError("peer cursor ledger must be a regular file")
        return descriptor

    def _read_records(
        self,
        descriptor: int,
        trust: CheckpointPeerTrust,
    ) -> tuple[CheckpointPeerCursorRecord, ...]:
        size = os.fstat(descriptor).st_size
        raw = os.pread(descriptor, size, 0)
        if not raw:
            return ()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("peer cursor ledger must be UTF-8 JSONL") from exc
        if not text.endswith("\n"):
            raise ValueError("peer cursor ledger has a truncated final record")
        records: list[CheckpointPeerCursorRecord] = []
        positions: dict[tuple[str, str], CheckpointPeerCursorPosition] = {}
        for line_number, line in enumerate(text.splitlines(), start=1):
            try:
                record = CheckpointPeerCursorRecord.model_validate_json(line)
            except ValueError as exc:
                raise ValueError(
                    f"invalid peer cursor record at line {line_number}: {exc}"
                ) from exc
            if record.registry_id != self.registry_id:
                raise ValueError("peer cursor registry_id does not match store")
            if record.cursor_sequence != len(records):
                raise ValueError("peer cursor sequence is not contiguous")
            expected_previous = records[-1].cursor_record_sha256 if records else None
            if record.previous_cursor_record_sha256 != expected_previous:
                raise ValueError("peer cursor hash chain is invalid")
            statement = verify_checkpoint_acknowledgement(
                record.acknowledgement,
                trust,
            )
            pair = _cursor_pair(statement)
            _validate_cursor_advance(positions.get(pair), record.acknowledgement)
            positions[pair] = _cursor_position(record.acknowledgement)
            records.append(record)
        return tuple(records)

    def _snapshot(
        self,
        records: tuple[CheckpointPeerCursorRecord, ...],
    ) -> CheckpointPeerCursorSnapshot:
        latest: dict[tuple[str, str], CheckpointPeerCursorPosition] = {}
        for record in records:
            latest[_cursor_pair(record.acknowledgement.statement)] = _cursor_position(
                record.acknowledgement
            )
        return CheckpointPeerCursorSnapshot(
            schema_version=SCHEMA_VERSION,
            registry_id=self.registry_id,
            cursors=records,
            cursor_count=len(records),
            head_cursor_record_sha256=(
                records[-1].cursor_record_sha256 if records else None
            ),
            positions=tuple(latest[pair] for pair in sorted(latest)),
        )

    def replay(
        self,
        trust: CheckpointPeerTrust,
    ) -> CheckpointPeerCursorSnapshot:
        """Replay every acknowledgement signature and monotonic cursor transition."""
        descriptor = self._open_for_replay()
        if descriptor is None:
            return self._snapshot(())
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH)
            return self._snapshot(self._read_records(descriptor, trust))
        finally:
            os.close(descriptor)

    def append(
        self,
        acknowledgement: SignedCheckpointAcknowledgement,
        trust: CheckpointPeerTrust,
    ) -> CheckpointPeerCursorRecord:
        """Verify and append one monotonic peer acknowledgement."""
        statement = verify_checkpoint_acknowledgement(acknowledgement, trust)
        if statement.registry_id != self.registry_id:
            raise ValueError("checkpoint acknowledgement registry_id does not match store")
        descriptor = self._open_for_append()
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            records = self._read_records(descriptor, trust)
            for record in reversed(records):
                if (
                    record.acknowledgement.signed_acknowledgement_sha256
                    == acknowledgement.signed_acknowledgement_sha256
                ):
                    return record
            pair = _cursor_pair(statement)
            current = next(
                (
                    _cursor_position(record.acknowledgement)
                    for record in reversed(records)
                    if _cursor_pair(record.acknowledgement.statement) == pair
                ),
                None,
            )
            _validate_cursor_advance(current, acknowledgement)
            payload = {
                "schema_version": SCHEMA_VERSION,
                "registry_id": self.registry_id,
                "cursor_sequence": len(records),
                "previous_cursor_record_sha256": (
                    records[-1].cursor_record_sha256 if records else None
                ),
                "acknowledgement": acknowledgement.model_dump(mode="json"),
            }
            record = CheckpointPeerCursorRecord(
                **payload,
                cursor_record_sha256=_canonical_sha256(payload),
            )
            encoded = (record.to_json() + "\n").encode()
            CheckpointRegistryStore._append_bytes(
                descriptor,
                encoded,
                original_size=os.fstat(descriptor).st_size,
            )
            return record
        finally:
            os.close(descriptor)

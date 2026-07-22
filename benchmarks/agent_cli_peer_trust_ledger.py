"""Versioned peer-trust rollover ledger for authenticated checkpoint sync."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.agent_cli_checkpoint_registry import (
    CheckpointPeerKey,
    CheckpointPeerTrust,
)
from benchmarks.agent_cli_comparison import SCHEMA_VERSION

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


class CheckpointPeerTrustRotationStatement(_FrozenModel):
    schema_version: int
    registry_id: str = Field(min_length=1, max_length=200)
    generation: int = Field(ge=2)
    predecessor_peer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    successor_peer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    minimum_distinct_peer_signatures: int = Field(ge=1)
    rotation_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_statement(self) -> CheckpointPeerTrustRotationStatement:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.registry_id, label="registry_id")
        if self.predecessor_peer_trust_sha256 == self.successor_peer_trust_sha256:
            raise ValueError("peer trust rotation must change peer trust")
        if self.rotation_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("peer trust rotation fingerprint does not match statement")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"rotation_sha256"})

    def signing_bytes(self) -> bytes:
        return _canonical_json(self.model_dump(mode="json")).encode()


class CheckpointPeerTrustRotationSigningRequest(_FrozenModel):
    peer_id: str = Field(min_length=1, max_length=200)
    eligible_key_ids: tuple[str, ...] = Field(min_length=1)
    statement: CheckpointPeerTrustRotationStatement
    signing_payload_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_request(self) -> CheckpointPeerTrustRotationSigningRequest:
        _validate_identifier(self.peer_id, label="peer_id")
        if tuple(sorted(set(self.eligible_key_ids))) != self.eligible_key_ids:
            raise ValueError("eligible peer rotation key IDs must be sorted and unique")
        expected = self.statement.signing_bytes()
        decoded = _decode_base64(
            self.signing_payload_base64,
            label="peer trust rotation signing payload",
            length=len(expected),
        )
        if decoded != expected:
            raise ValueError("peer trust rotation payload does not match statement")
        return self


class CheckpointPeerTrustRotationTemplate(_FrozenModel):
    schema_version: int
    generation: int = Field(ge=2)
    predecessor_peer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    successor_peer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    minimum_distinct_peer_signatures: int = Field(ge=1)
    statement: CheckpointPeerTrustRotationStatement
    requests: tuple[CheckpointPeerTrustRotationSigningRequest, ...] = Field(
        min_length=1
    )
    signatures_completed: Literal[False] = False

    @model_validator(mode="after")
    def validate_template(self) -> CheckpointPeerTrustRotationTemplate:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if self.generation != self.statement.generation:
            raise ValueError("peer trust rotation template generation does not match")
        if self.predecessor_peer_trust_sha256 != (
            self.statement.predecessor_peer_trust_sha256
        ):
            raise ValueError("peer trust rotation template predecessor does not match")
        if self.successor_peer_trust_sha256 != (
            self.statement.successor_peer_trust_sha256
        ):
            raise ValueError("peer trust rotation template successor does not match")
        if self.minimum_distinct_peer_signatures != (
            self.statement.minimum_distinct_peer_signatures
        ):
            raise ValueError("peer trust rotation template quorum does not match")
        if tuple(sorted(self.requests, key=lambda item: item.peer_id)) != self.requests:
            raise ValueError("peer trust rotation requests must be sorted")
        peer_ids = [request.peer_id for request in self.requests]
        if len(peer_ids) != len(set(peer_ids)):
            raise ValueError("peer trust rotation requests must use distinct peers")
        if any(request.statement != self.statement for request in self.requests):
            raise ValueError("peer trust rotation requests use different statements")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class CheckpointPeerRotationSignature(_FrozenModel):
    peer_id: str = Field(min_length=1, max_length=200)
    key_id: str = Field(min_length=1, max_length=200)
    signature_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_signature(self) -> CheckpointPeerRotationSignature:
        _validate_identifier(self.peer_id, label="peer_id")
        _validate_identifier(self.key_id, label="key_id")
        _decode_base64(
            self.signature_base64,
            label="peer trust rotation signature",
            length=64,
        )
        return self


def _signature_identity(
    signature: CheckpointPeerRotationSignature,
) -> tuple[str, str]:
    return signature.peer_id, signature.key_id


class CheckpointPeerTrustRotationCertificate(_FrozenModel):
    schema_version: int
    statement: CheckpointPeerTrustRotationStatement
    signatures: tuple[CheckpointPeerRotationSignature, ...] = Field(min_length=1)
    rotation_certificate_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_certificate(self) -> CheckpointPeerTrustRotationCertificate:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if tuple(sorted(self.signatures, key=_signature_identity)) != self.signatures:
            raise ValueError("peer trust rotation signatures must be sorted")
        peer_ids = [signature.peer_id for signature in self.signatures]
        if len(peer_ids) != len(set(peer_ids)):
            raise ValueError("peer trust rotation signatures must use distinct peers")
        if self.rotation_certificate_sha256 != _canonical_sha256(
            self._binding_payload()
        ):
            raise ValueError("peer trust rotation certificate fingerprint does not match")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"rotation_certificate_sha256"})


class CheckpointPeerTrustGeneration(_FrozenModel):
    schema_version: int
    generation: int = Field(ge=1)
    trust: CheckpointPeerTrust
    rotation: CheckpointPeerTrustRotationCertificate | None = None

    @model_validator(mode="after")
    def validate_generation(self) -> CheckpointPeerTrustGeneration:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if (self.generation == 1) != (self.rotation is None):
            raise ValueError("only genesis peer trust may omit a rotation certificate")
        return self


class CheckpointPeerTrustLedger(_FrozenModel):
    schema_version: int
    registry_id: str = Field(min_length=1, max_length=200)
    generations: tuple[CheckpointPeerTrustGeneration, ...] = Field(min_length=1)
    active_generation: int = Field(ge=1)
    ledger_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_ledger(self) -> CheckpointPeerTrustLedger:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.registry_id, label="registry_id")
        _validate_generation_chain(self.generations)
        if any(
            generation.trust.registry_id != self.registry_id
            for generation in self.generations
        ):
            raise ValueError("peer trust ledger generations use another registry")
        if self.active_generation != self.generations[-1].generation:
            raise ValueError("active_generation must identify the latest peer trust")
        if self.ledger_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("peer trust ledger fingerprint does not match generations")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"ledger_sha256"})

    @property
    def active_trust(self) -> CheckpointPeerTrust:
        return self.generations[-1].trust

    def resolve_peer_trust(self, peer_trust_sha256: str) -> CheckpointPeerTrust:
        for generation in self.generations:
            if generation.trust.peer_trust_sha256 == peer_trust_sha256:
                return generation.trust
        raise ValueError(
            f"peer trust {peer_trust_sha256} is not present in peer trust ledger"
        )

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _active_keys_by_peer(
    trust: CheckpointPeerTrust,
) -> dict[str, tuple[CheckpointPeerKey, ...]]:
    grouped: dict[str, list[CheckpointPeerKey]] = {}
    for key in trust.keys:
        if key.status == "active":
            grouped.setdefault(key.peer_id, []).append(key)
    return {
        peer_id: tuple(sorted(keys, key=lambda key: key.key_id))
        for peer_id, keys in grouped.items()
    }


def _rotation_statement(
    predecessor: CheckpointPeerTrust,
    successor: CheckpointPeerTrust,
    *,
    generation: int,
) -> CheckpointPeerTrustRotationStatement:
    predecessor = CheckpointPeerTrust.model_validate(
        predecessor.model_dump(mode="json")
    )
    successor = CheckpointPeerTrust.model_validate(successor.model_dump(mode="json"))
    if generation < 2:
        raise ValueError("peer trust rotation generation must be at least 2")
    if predecessor.registry_id != successor.registry_id:
        raise ValueError("peer trust rotation changes registry_id")
    if predecessor.peer_trust_sha256 == successor.peer_trust_sha256:
        raise ValueError("peer trust rotation must change peer trust")
    active_peers = _active_keys_by_peer(predecessor)
    minimum = len(active_peers) // 2 + 1
    payload = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": predecessor.registry_id,
        "generation": generation,
        "predecessor_peer_trust_sha256": predecessor.peer_trust_sha256,
        "successor_peer_trust_sha256": successor.peer_trust_sha256,
        "minimum_distinct_peer_signatures": minimum,
    }
    return CheckpointPeerTrustRotationStatement.model_validate(
        {**payload, "rotation_sha256": _canonical_sha256(payload)}
    )


def build_checkpoint_peer_trust_rotation_template(
    predecessor: CheckpointPeerTrust,
    successor: CheckpointPeerTrust,
    *,
    generation: int,
) -> CheckpointPeerTrustRotationTemplate:
    """Create one detached signing request per active predecessor peer."""
    statement = _rotation_statement(
        predecessor,
        successor,
        generation=generation,
    )
    requests = tuple(
        CheckpointPeerTrustRotationSigningRequest(
            peer_id=peer_id,
            eligible_key_ids=tuple(key.key_id for key in keys),
            statement=statement,
            signing_payload_base64=base64.b64encode(
                statement.signing_bytes()
            ).decode(),
        )
        for peer_id, keys in sorted(_active_keys_by_peer(predecessor).items())
    )
    return CheckpointPeerTrustRotationTemplate(
        schema_version=SCHEMA_VERSION,
        generation=generation,
        predecessor_peer_trust_sha256=predecessor.peer_trust_sha256,
        successor_peer_trust_sha256=successor.peer_trust_sha256,
        minimum_distinct_peer_signatures=(
            statement.minimum_distinct_peer_signatures
        ),
        statement=statement,
        requests=requests,
    )


def verify_checkpoint_peer_trust_rotation_certificate(
    certificate: CheckpointPeerTrustRotationCertificate,
    predecessor: CheckpointPeerTrust,
    successor: CheckpointPeerTrust,
    *,
    generation: int,
) -> None:
    """Verify one strict-majority rollover against the predecessor key set."""
    certificate = CheckpointPeerTrustRotationCertificate.model_validate(
        certificate.model_dump(mode="json")
    )
    expected = _rotation_statement(
        predecessor,
        successor,
        generation=generation,
    )
    if certificate.statement != expected:
        raise ValueError("peer trust rotation certificate does not match generation")
    if len(certificate.signatures) < expected.minimum_distinct_peer_signatures:
        raise ValueError("peer trust rotation strict-majority quorum is incomplete")
    active_keys = {
        (key.peer_id, key.key_id): key
        for key in predecessor.keys
        if key.status == "active"
    }
    for signature in certificate.signatures:
        key = active_keys.get(_signature_identity(signature))
        if key is None:
            raise ValueError("peer trust rotation signature is not an active predecessor key")
        try:
            Ed25519PublicKey.from_public_bytes(
                _decode_base64(
                    key.public_key_base64,
                    label="peer public key",
                    length=32,
                )
            ).verify(
                _decode_base64(
                    signature.signature_base64,
                    label="peer trust rotation signature",
                    length=64,
                ),
                certificate.statement.signing_bytes(),
            )
        except (InvalidSignature, ValueError) as exc:
            raise ValueError(
                f"peer trust rotation signature is invalid: {signature.peer_id}"
            ) from exc


def build_checkpoint_peer_trust_rotation_certificate(
    template: CheckpointPeerTrustRotationTemplate,
    predecessor: CheckpointPeerTrust,
    successor: CheckpointPeerTrust,
    signatures: tuple[CheckpointPeerRotationSignature, ...],
) -> CheckpointPeerTrustRotationCertificate:
    """Normalize and verify detached strict-majority rollover signatures."""
    expected_template = build_checkpoint_peer_trust_rotation_template(
        predecessor,
        successor,
        generation=template.generation,
    )
    if template != expected_template:
        raise ValueError("peer trust rotation template does not match trusts")
    ordered = tuple(sorted(signatures, key=_signature_identity))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "statement": template.statement.model_dump(mode="json"),
        "signatures": [signature.model_dump(mode="json") for signature in ordered],
    }
    certificate = CheckpointPeerTrustRotationCertificate.model_validate(
        {
            **payload,
            "rotation_certificate_sha256": _canonical_sha256(payload),
        }
    )
    verify_checkpoint_peer_trust_rotation_certificate(
        certificate,
        predecessor,
        successor,
        generation=template.generation,
    )
    return certificate


def _validate_generation_chain(
    generations: tuple[CheckpointPeerTrustGeneration, ...],
) -> None:
    if not generations:
        raise ValueError("peer trust ledger requires at least one generation")
    fingerprints: set[str] = set()
    registry_id = generations[0].trust.registry_id
    for index, generation in enumerate(generations):
        if generation.generation != index + 1:
            raise ValueError("peer trust generations must be contiguous and ordered")
        if generation.trust.registry_id != registry_id:
            raise ValueError("peer trust generations change registry_id")
        fingerprint = generation.trust.peer_trust_sha256
        if fingerprint in fingerprints:
            raise ValueError("peer trust generations must not reuse peer trust")
        fingerprints.add(fingerprint)
        if index == 0:
            if generation.rotation is not None:
                raise ValueError("genesis peer trust must not have a rotation")
            continue
        rotation = generation.rotation
        if rotation is None:
            raise ValueError("peer trust generation is missing its rotation")
        verify_checkpoint_peer_trust_rotation_certificate(
            rotation,
            generations[index - 1].trust,
            generation.trust,
            generation=generation.generation,
        )


def build_checkpoint_peer_trust_ledger(
    generations: tuple[CheckpointPeerTrustGeneration, ...],
) -> CheckpointPeerTrustLedger:
    """Verify and self-fingerprint a complete peer-trust generation chain."""
    _validate_generation_chain(generations)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": generations[0].trust.registry_id,
        "generations": [generation.model_dump(mode="json") for generation in generations],
        "active_generation": generations[-1].generation,
    }
    return CheckpointPeerTrustLedger.model_validate(
        {**payload, "ledger_sha256": _canonical_sha256(payload)}
    )

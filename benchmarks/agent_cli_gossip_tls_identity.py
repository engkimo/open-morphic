"""Peer-signed TLS certificate enrollment for checkpoint gossip."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
from datetime import UTC, datetime
from typing import Literal

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.x509.oid import ExtendedKeyUsageOID
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
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _canonical_sha256(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def _validate_identifier(value: str, *, label: str) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be non-blank without surrounding whitespace")


def _decode_base64(value: str, *, label: str, length: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be canonical base64") from exc
    if len(decoded) != length or base64.b64encode(decoded).decode() != value:
        raise ValueError(f"{label} must encode exactly {length} bytes")
    return decoded


def _load_certificate(certificate: bytes) -> x509.Certificate:
    try:
        if b"-----BEGIN CERTIFICATE-----" in certificate:
            certificates = x509.load_pem_x509_certificates(certificate)
            if len(certificates) != 1:
                raise ValueError("TLS enrollment must contain exactly one certificate")
            return certificates[0]
        return x509.load_der_x509_certificate(certificate)
    except ValueError as exc:
        raise ValueError("TLS enrollment certificate is invalid") from exc


def _certificate_metadata(certificate_bytes: bytes) -> dict[str, object]:
    certificate = _load_certificate(certificate_bytes)
    try:
        constraints = certificate.extensions.get_extension_for_class(x509.BasicConstraints).value
        san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        usages = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        key_usage = certificate.extensions.get_extension_for_class(x509.KeyUsage).value
    except x509.ExtensionNotFound as exc:
        raise ValueError("TLS leaf certificate is missing required extensions") from exc
    if constraints.ca:
        raise ValueError("TLS enrollment certificate must be a leaf certificate")
    required = {ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.SERVER_AUTH}
    if not required.issubset(set(usages)):
        raise ValueError("TLS leaf certificate must allow client and server authentication")
    if not key_usage.digital_signature:
        raise ValueError("TLS leaf certificate must allow digital signatures")
    dns_names = tuple(sorted(set(san.get_values_for_type(x509.DNSName))))
    ip_addresses = tuple(
        sorted(
            {str(value) for value in san.get_values_for_type(x509.IPAddress)},
            key=ipaddress.ip_address,
        )
    )
    if not dns_names and not ip_addresses:
        raise ValueError("TLS leaf certificate must declare a DNS or IP SAN")
    der = certificate.public_bytes(serialization.Encoding.DER)
    spki = certificate.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return {
        "certificate_sha256": hashlib.sha256(der).hexdigest(),
        "spki_sha256": hashlib.sha256(spki).hexdigest(),
        "subject": certificate.subject.rfc4514_string(),
        "issuer": certificate.issuer.rfc4514_string(),
        "serial_number": format(certificate.serial_number, "x"),
        "not_valid_before": certificate.not_valid_before_utc.astimezone(UTC).isoformat(),
        "not_valid_after": certificate.not_valid_after_utc.astimezone(UTC).isoformat(),
        "dns_names": dns_names,
        "ip_addresses": ip_addresses,
        "extended_key_usages": ("client_auth", "server_auth"),
    }


class CheckpointPeerTlsEnrollmentStatement(_FrozenModel):
    schema_version: int
    registry_id: str = Field(min_length=1, max_length=200)
    peer_id: str = Field(min_length=1, max_length=200)
    generation: int = Field(ge=1)
    previous_enrollment_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    peer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    certificate_sha256: str = Field(pattern=_SHA256_PATTERN)
    spki_sha256: str = Field(pattern=_SHA256_PATTERN)
    subject: str = Field(min_length=1)
    issuer: str = Field(min_length=1)
    serial_number: str = Field(min_length=1)
    not_valid_before: str = Field(min_length=1)
    not_valid_after: str = Field(min_length=1)
    dns_names: tuple[str, ...]
    ip_addresses: tuple[str, ...]
    extended_key_usages: tuple[Literal["client_auth", "server_auth"], ...]
    statement_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_statement(self) -> CheckpointPeerTlsEnrollmentStatement:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.registry_id, label="registry_id")
        _validate_identifier(self.peer_id, label="peer_id")
        if (self.generation == 1) != (self.previous_enrollment_sha256 is None):
            raise ValueError("TLS enrollment generation and predecessor do not match")
        if tuple(sorted(set(self.dns_names))) != self.dns_names:
            raise ValueError("TLS enrollment DNS names must be sorted and unique")
        if tuple(sorted(set(self.ip_addresses), key=ipaddress.ip_address)) != self.ip_addresses:
            raise ValueError("TLS enrollment IP addresses must be sorted and unique")
        if self.extended_key_usages != ("client_auth", "server_auth"):
            raise ValueError("TLS enrollment usages must bind client and server authentication")
        if self.statement_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("TLS enrollment statement fingerprint does not match")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"statement_sha256"})

    def signing_bytes(self) -> bytes:
        return _canonical_json(self.model_dump(mode="json")).encode()


class CheckpointPeerTlsEnrollmentTemplate(_FrozenModel):
    statement: CheckpointPeerTlsEnrollmentStatement
    eligible_key_ids: tuple[str, ...] = Field(min_length=1)
    signing_payload_base64: str = Field(min_length=1)
    signatures_completed: Literal[False] = False

    @model_validator(mode="after")
    def validate_template(self) -> CheckpointPeerTlsEnrollmentTemplate:
        if tuple(sorted(set(self.eligible_key_ids))) != self.eligible_key_ids:
            raise ValueError("eligible peer key IDs must be sorted and unique")
        expected = base64.b64encode(self.statement.signing_bytes()).decode()
        if self.signing_payload_base64 != expected:
            raise ValueError("TLS enrollment signing payload does not match statement")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class CheckpointPeerTlsEnrollment(_FrozenModel):
    statement: CheckpointPeerTlsEnrollmentStatement
    key_id: str = Field(min_length=1, max_length=200)
    signature_base64: str = Field(min_length=1)
    enrollment_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_enrollment(self) -> CheckpointPeerTlsEnrollment:
        _validate_identifier(self.key_id, label="key_id")
        _decode_base64(self.signature_base64, label="TLS enrollment signature", length=64)
        if self.enrollment_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("TLS enrollment fingerprint does not match")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"enrollment_sha256"})

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class CheckpointPeerTlsRevocationStatement(_FrozenModel):
    schema_version: int
    registry_id: str = Field(min_length=1, max_length=200)
    peer_id: str = Field(min_length=1, max_length=200)
    generation: int = Field(ge=1)
    enrollment_sha256: str = Field(pattern=_SHA256_PATTERN)
    peer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    reason: str = Field(min_length=1, max_length=500)
    revoked_at: str = Field(min_length=1)
    statement_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_statement(self) -> CheckpointPeerTlsRevocationStatement:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.peer_id, label="peer_id")
        _validate_identifier(self.reason, label="reason")
        if self.statement_sha256 != _canonical_sha256(
            self.model_dump(mode="json", exclude={"statement_sha256"})
        ):
            raise ValueError("TLS revocation statement fingerprint does not match")
        return self

    def signing_bytes(self) -> bytes:
        return _canonical_json(self.model_dump(mode="json")).encode()


class CheckpointPeerTlsRevocation(_FrozenModel):
    statement: CheckpointPeerTlsRevocationStatement
    key_id: str = Field(min_length=1, max_length=200)
    signature_base64: str = Field(min_length=1)
    revocation_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_revocation(self) -> CheckpointPeerTlsRevocation:
        _decode_base64(self.signature_base64, label="TLS revocation signature", length=64)
        payload = self.model_dump(mode="json", exclude={"revocation_sha256"})
        if self.revocation_sha256 != _canonical_sha256(payload):
            raise ValueError("TLS revocation fingerprint does not match")
        return self


class CheckpointPeerTlsRevocationTemplate(_FrozenModel):
    statement: CheckpointPeerTlsRevocationStatement
    eligible_key_ids: tuple[str, ...] = Field(min_length=1)
    signing_payload_base64: str = Field(min_length=1)
    signatures_completed: Literal[False] = False

    @model_validator(mode="after")
    def validate_template(self) -> CheckpointPeerTlsRevocationTemplate:
        if tuple(sorted(set(self.eligible_key_ids))) != self.eligible_key_ids:
            raise ValueError("eligible peer key IDs must be sorted and unique")
        expected = base64.b64encode(self.statement.signing_bytes()).decode()
        if self.signing_payload_base64 != expected:
            raise ValueError("TLS revocation signing payload does not match statement")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def build_checkpoint_peer_tls_revocation_template(
    tls_trust: CheckpointPeerTlsTrust,
    peer_trust: CheckpointPeerTrust,
    *,
    peer_id: str,
    generation: int,
    reason: str,
    revoked_at: str,
) -> CheckpointPeerTlsRevocationTemplate:
    """Create a private-key-free request to revoke one enrolled generation."""
    enrollment = next(
        (item for item in tls_trust.enrollments
         if item.statement.peer_id == peer_id and item.statement.generation == generation),
        None,
    )
    if enrollment is None:
        raise ValueError("TLS revocation target is not enrolled")
    active_keys = tuple(sorted(key.key_id for key in _active_peer_keys(peer_trust, peer_id)))
    if not active_keys:
        raise ValueError("TLS revocation peer has no active identity key")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": tls_trust.registry_id,
        "peer_id": peer_id,
        "generation": generation,
        "enrollment_sha256": enrollment.enrollment_sha256,
        "peer_trust_sha256": tls_trust.peer_trust_sha256,
        "reason": reason,
        "revoked_at": revoked_at,
    }
    statement = CheckpointPeerTlsRevocationStatement.model_validate(
        {**payload, "statement_sha256": _canonical_sha256(payload)}
    )
    return CheckpointPeerTlsRevocationTemplate(
        statement=statement,
        eligible_key_ids=active_keys,
        signing_payload_base64=base64.b64encode(statement.signing_bytes()).decode(),
    )


def _enrollment_identity(enrollment: CheckpointPeerTlsEnrollment) -> tuple[str, int]:
    return enrollment.statement.peer_id, enrollment.statement.generation


class CheckpointPeerTlsTrust(_FrozenModel):
    schema_version: int
    registry_id: str = Field(min_length=1, max_length=200)
    peer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    enrollments: tuple[CheckpointPeerTlsEnrollment, ...] = Field(min_length=1)
    revocations: tuple[CheckpointPeerTlsRevocation, ...] = ()
    tls_trust_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_trust(self) -> CheckpointPeerTlsTrust:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.registry_id, label="registry_id")
        if tuple(sorted(self.enrollments, key=_enrollment_identity)) != self.enrollments:
            raise ValueError("TLS enrollments must be sorted")
        identities = [_enrollment_identity(item) for item in self.enrollments]
        if len(identities) != len(set(identities)):
            raise ValueError("TLS enrollment generations must be unique")
        for index, enrollment in enumerate(self.enrollments):
            statement = enrollment.statement
            if statement.registry_id != self.registry_id:
                raise ValueError("TLS enrollment uses another registry")
            if statement.peer_trust_sha256 != self.peer_trust_sha256:
                raise ValueError("TLS enrollment uses another peer trust")
            predecessor = next(
                (
                    candidate
                    for candidate in self.enrollments[:index]
                    if candidate.statement.peer_id == statement.peer_id
                    and candidate.statement.generation == statement.generation - 1
                ),
                None,
            )
            if statement.generation > 1 and (
                predecessor is None
                or statement.previous_enrollment_sha256 != predecessor.enrollment_sha256
            ):
                raise ValueError("TLS enrollment predecessor is missing or invalid")
        targets = {
            (item.statement.peer_id, item.statement.generation, item.statement.enrollment_sha256)
            for item in self.revocations
        }
        if len(targets) != len(self.revocations):
            raise ValueError("duplicate TLS revocation target")
        enrollment_targets = {
            (item.statement.peer_id, item.statement.generation, item.enrollment_sha256)
            for item in self.enrollments
        }
        if not targets.issubset(enrollment_targets):
            raise ValueError("TLS revocation target is not enrolled")
        active = [self.active_enrollment(peer) for peer in self.peer_ids()]
        if len({item.statement.certificate_sha256 for item in active}) != len(active):
            raise ValueError("active TLS certificate pins must be unique across peers")
        if len({item.statement.spki_sha256 for item in active}) != len(active):
            raise ValueError("active TLS SPKI pins must be unique across peers")
        if self.tls_trust_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("TLS trust fingerprint does not match")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"tls_trust_sha256"})

    def peer_ids(self) -> tuple[str, ...]:
        return tuple(sorted({item.statement.peer_id for item in self.enrollments}))

    def active_enrollment(self, peer_id: str) -> CheckpointPeerTlsEnrollment:
        matches = [item for item in self.enrollments if item.statement.peer_id == peer_id]
        if not matches:
            raise ValueError(f"peer has no active TLS enrollment: {peer_id}")
        revoked = {
            (item.statement.peer_id, item.statement.generation, item.statement.enrollment_sha256)
            for item in self.revocations
        }
        for item in reversed(matches):
            if (
                item.statement.peer_id,
                item.statement.generation,
                item.enrollment_sha256,
            ) not in revoked:
                return item
        raise ValueError(f"peer has no active TLS enrollment: {peer_id}")

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _active_peer_keys(
    peer_trust: CheckpointPeerTrust,
    peer_id: str,
) -> tuple[CheckpointPeerKey, ...]:
    return tuple(
        key for key in peer_trust.keys if key.peer_id == peer_id and key.status == "active"
    )


def _verify_enrollment_signature(
    enrollment: CheckpointPeerTlsEnrollment,
    peer_trust: CheckpointPeerTrust,
) -> None:
    keys = {key.key_id: key for key in _active_peer_keys(peer_trust, enrollment.statement.peer_id)}
    key = keys.get(enrollment.key_id)
    if key is None:
        raise ValueError("TLS enrollment signature key is not active for peer")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode_base64(key.public_key_base64, label="peer public key", length=32)
        ).verify(
            _decode_base64(
                enrollment.signature_base64,
                label="TLS enrollment signature",
                length=64,
            ),
            enrollment.statement.signing_bytes(),
        )
    except InvalidSignature as exc:
        raise ValueError("TLS enrollment signature is invalid") from exc


def _verify_revocation_signature(
    revocation: CheckpointPeerTlsRevocation,
    peer_trust: CheckpointPeerTrust,
) -> None:
    keys = {key.key_id: key for key in _active_peer_keys(peer_trust, revocation.statement.peer_id)}
    key = keys.get(revocation.key_id)
    if key is None:
        raise ValueError("TLS revocation signature key is not active for peer")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode_base64(key.public_key_base64, label="peer public key", length=32)
        ).verify(
            _decode_base64(
                revocation.signature_base64, label="TLS revocation signature", length=64
            ),
            revocation.statement.signing_bytes(),
        )
    except InvalidSignature as exc:
        raise ValueError("TLS revocation signature is invalid") from exc


def build_signed_checkpoint_peer_tls_revocation(
    template: CheckpointPeerTlsRevocationTemplate,
    peer_trust: CheckpointPeerTrust,
    *,
    key_id: str,
    signature_base64: str,
) -> CheckpointPeerTlsRevocation:
    """Verify a peer signature and finalize a TLS revocation artifact."""
    if key_id not in template.eligible_key_ids:
        raise ValueError("TLS revocation signature key is not eligible")
    payload = {
        "statement": template.statement.model_dump(mode="json"),
        "key_id": key_id,
        "signature_base64": signature_base64,
    }
    revocation = CheckpointPeerTlsRevocation.model_validate(
        {**payload, "revocation_sha256": _canonical_sha256(payload)}
    )
    _verify_revocation_signature(revocation, peer_trust)
    return revocation


def build_checkpoint_peer_tls_enrollment_template(
    certificate: bytes,
    peer_trust: CheckpointPeerTrust,
    *,
    peer_id: str,
    generation: int,
    predecessor: CheckpointPeerTlsEnrollment | None = None,
) -> CheckpointPeerTlsEnrollmentTemplate:
    """Bind a validated TLS leaf certificate to a peer identity signing request."""
    peer_trust = CheckpointPeerTrust.model_validate(peer_trust.model_dump(mode="json"))
    active_keys = _active_peer_keys(peer_trust, peer_id)
    if not active_keys:
        raise ValueError("TLS enrollment peer has no active identity key")
    if generation == 1 and predecessor is not None:
        raise ValueError("first TLS enrollment cannot declare a predecessor")
    if generation > 1 and (
        predecessor is None
        or predecessor.statement.peer_id != peer_id
        or predecessor.statement.generation != generation - 1
    ):
        raise ValueError("TLS enrollment predecessor does not match generation")
    metadata = _certificate_metadata(certificate)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": peer_trust.registry_id,
        "peer_id": peer_id,
        "generation": generation,
        "previous_enrollment_sha256": (
            predecessor.enrollment_sha256 if predecessor is not None else None
        ),
        "peer_trust_sha256": peer_trust.peer_trust_sha256,
        **metadata,
    }
    statement = CheckpointPeerTlsEnrollmentStatement.model_validate(
        {**payload, "statement_sha256": _canonical_sha256(payload)}
    )
    return CheckpointPeerTlsEnrollmentTemplate(
        statement=statement,
        eligible_key_ids=tuple(sorted(key.key_id for key in active_keys)),
        signing_payload_base64=base64.b64encode(statement.signing_bytes()).decode(),
    )


def build_signed_checkpoint_peer_tls_enrollment(
    template: CheckpointPeerTlsEnrollmentTemplate,
    certificate: bytes,
    peer_trust: CheckpointPeerTrust,
    *,
    key_id: str,
    signature_base64: str,
    predecessor: CheckpointPeerTlsEnrollment | None = None,
) -> CheckpointPeerTlsEnrollment:
    """Verify an identity signature and finalize a TLS enrollment generation."""
    expected = build_checkpoint_peer_tls_enrollment_template(
        certificate,
        peer_trust,
        peer_id=template.statement.peer_id,
        generation=template.statement.generation,
        predecessor=predecessor,
    )
    if expected.statement != template.statement:
        raise ValueError("TLS enrollment template does not match certificate or trust")
    if key_id not in template.eligible_key_ids:
        raise ValueError("TLS enrollment signature key is not eligible")
    payload = {
        "statement": template.statement.model_dump(mode="json"),
        "key_id": key_id,
        "signature_base64": signature_base64,
    }
    enrollment = CheckpointPeerTlsEnrollment.model_validate(
        {**payload, "enrollment_sha256": _canonical_sha256(payload)}
    )
    _verify_enrollment_signature(enrollment, peer_trust)
    return enrollment


def build_checkpoint_peer_tls_trust(
    peer_trust: CheckpointPeerTrust,
    enrollments: tuple[CheckpointPeerTlsEnrollment, ...],
    revocations: tuple[CheckpointPeerTlsRevocation, ...] = (),
) -> CheckpointPeerTlsTrust:
    """Verify signed enrollment chains and publish deterministic TLS pins."""
    peer_trust = CheckpointPeerTrust.model_validate(peer_trust.model_dump(mode="json"))
    normalized = tuple(
        sorted(
            (
                CheckpointPeerTlsEnrollment.model_validate(item.model_dump(mode="json"))
                for item in enrollments
            ),
            key=_enrollment_identity,
        )
    )
    for enrollment in normalized:
        _verify_enrollment_signature(enrollment, peer_trust)
    normalized_revocations = tuple(
        sorted(
            (
                CheckpointPeerTlsRevocation.model_validate(item.model_dump(mode="json"))
                for item in revocations
            ),
            key=lambda item: (item.statement.peer_id, item.statement.generation),
        )
    )
    for revocation in normalized_revocations:
        if revocation.statement.peer_trust_sha256 != peer_trust.peer_trust_sha256:
            raise ValueError("TLS revocation uses another peer trust")
        _verify_revocation_signature(revocation, peer_trust)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": peer_trust.registry_id,
        "peer_trust_sha256": peer_trust.peer_trust_sha256,
        "enrollments": [item.model_dump(mode="json") for item in normalized],
        "revocations": [item.model_dump(mode="json") for item in normalized_revocations],
    }
    return CheckpointPeerTlsTrust.model_validate(
        {**payload, "tls_trust_sha256": _canonical_sha256(payload)}
    )


def verify_checkpoint_peer_tls_trust(
    tls_trust: CheckpointPeerTlsTrust,
    peer_trust: CheckpointPeerTrust,
) -> None:
    """Reverify every enrollment signature against an exact peer trust artifact."""
    verified = build_checkpoint_peer_tls_trust(
        peer_trust, tls_trust.enrollments, tls_trust.revocations
    )
    if verified != tls_trust:
        raise ValueError("TLS trust does not match checkpoint peer trust")


def certificate_fingerprints(certificate: bytes) -> tuple[str, str]:
    """Return the normalized DER certificate and SPKI SHA-256 pins."""
    metadata = _certificate_metadata(certificate)
    return str(metadata["certificate_sha256"]), str(metadata["spki_sha256"])


def verify_active_tls_certificate(
    certificate: bytes,
    tls_trust: CheckpointPeerTlsTrust,
    peer_id: str,
) -> None:
    """Require a leaf certificate to match both active peer pins."""
    certificate_sha256, spki_sha256 = certificate_fingerprints(certificate)
    active = tls_trust.active_enrollment(peer_id).statement
    if certificate_sha256 != active.certificate_sha256 or spki_sha256 != active.spki_sha256:
        raise ValueError("active peer TLS certificate pin does not match")


def resolve_active_tls_peer(
    certificate: bytes,
    tls_trust: CheckpointPeerTlsTrust,
) -> str:
    """Resolve an authenticated leaf to exactly one active peer identity."""
    certificate_sha256, spki_sha256 = certificate_fingerprints(certificate)
    matches = [
        peer_id
        for peer_id in tls_trust.peer_ids()
        if (
            tls_trust.active_enrollment(peer_id).statement.certificate_sha256 == certificate_sha256
            and tls_trust.active_enrollment(peer_id).statement.spki_sha256 == spki_sha256
        )
    ]
    if len(matches) != 1:
        raise ValueError("TLS certificate does not match an active peer enrollment")
    return matches[0]


def validate_checkpoint_peer_tls_expiry(
    tls_trust: CheckpointPeerTlsTrust,
    *,
    now: datetime | None = None,
    warning_window_seconds: int = 0,
) -> tuple[tuple[str, int, str, int], ...]:
    """Reject expired active leaves and return deterministic pre-expiry warnings."""
    if warning_window_seconds < 0:
        raise ValueError("warning_window_seconds must be non-negative")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    warnings: list[tuple[str, int, str, int]] = []
    for peer_id in tls_trust.peer_ids():
        statement = tls_trust.active_enrollment(peer_id).statement
        expires = datetime.fromisoformat(
            statement.not_valid_after.replace("Z", "+00:00")
        ).astimezone(UTC)
        seconds = int((expires - current).total_seconds())
        if seconds < 0:
            raise ValueError(f"active TLS certificate is expired: {peer_id}")
        if seconds <= warning_window_seconds:
            warnings.append((peer_id, statement.generation, statement.not_valid_after, seconds))
    return tuple(warnings)

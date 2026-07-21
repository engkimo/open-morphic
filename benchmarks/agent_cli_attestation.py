"""Offline Ed25519 attestations for independent benchmark reviews."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.agent_cli_adjudication import AdjudicationReviews, ReviewDecision
from benchmarks.agent_cli_comparison import SCHEMA_VERSION
from benchmarks.agent_cli_review_policy import ReviewerPolicy, validate_reviewer_separation

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
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{label} must be canonical base64") from exc
    if len(decoded) != length or base64.b64encode(decoded).decode() != value:
        raise ValueError(f"{label} must encode exactly {length} bytes")
    return decoded


class ReviewerPublicKeyDeclaration(_FrozenModel):
    reviewer_id: str = Field(min_length=1, max_length=200)
    key_id: str = Field(min_length=1, max_length=200)
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: str = Field(min_length=1)
    status: Literal["active", "revoked"] = "active"

    @model_validator(mode="after")
    def validate_key(self) -> ReviewerPublicKeyDeclaration:
        _validate_identifier(self.reviewer_id, label="reviewer_id")
        _validate_identifier(self.key_id, label="key_id")
        _decode_base64(self.public_key_base64, label="public_key_base64", length=32)
        return self


class ReviewerTrustDeclaration(_FrozenModel):
    schema_version: int
    benchmark_id: str = Field(min_length=1)
    review_policy_sha256: str = Field(pattern=_SHA256_PATTERN)
    reviewer_authority_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    keys: tuple[ReviewerPublicKeyDeclaration, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_declaration(self) -> ReviewerTrustDeclaration:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        identities = [(key.reviewer_id, key.key_id) for key in self.keys]
        if len(identities) != len(set(identities)):
            raise ValueError("reviewer key identities must be unique")
        if len({key.key_id for key in self.keys}) != len(self.keys):
            raise ValueError("key_id values must be globally unique")
        return self


class ReviewerPublicKey(_FrozenModel):
    reviewer_id: str = Field(min_length=1, max_length=200)
    key_id: str = Field(min_length=1, max_length=200)
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: str = Field(min_length=1)
    public_key_sha256: str = Field(pattern=_SHA256_PATTERN)
    status: Literal["active", "revoked"]

    @model_validator(mode="after")
    def validate_fingerprint(self) -> ReviewerPublicKey:
        declaration = ReviewerPublicKeyDeclaration(
            reviewer_id=self.reviewer_id,
            key_id=self.key_id,
            algorithm=self.algorithm,
            public_key_base64=self.public_key_base64,
            status=self.status,
        )
        decoded = _decode_base64(
            declaration.public_key_base64,
            label="public_key_base64",
            length=32,
        )
        if hashlib.sha256(decoded).hexdigest() != self.public_key_sha256:
            raise ValueError("public key fingerprint does not match key")
        return self


class ReviewerTrust(_FrozenModel):
    schema_version: int
    benchmark_id: str = Field(min_length=1)
    review_policy_sha256: str = Field(pattern=_SHA256_PATTERN)
    reviewer_authority_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    keys: tuple[ReviewerPublicKey, ...] = Field(min_length=1)
    reviewer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_fingerprint(self) -> ReviewerTrust:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        ReviewerTrustDeclaration(
            schema_version=self.schema_version,
            benchmark_id=self.benchmark_id,
            review_policy_sha256=self.review_policy_sha256,
            reviewer_authority_sha256=self.reviewer_authority_sha256,
            keys=tuple(
                ReviewerPublicKeyDeclaration(
                    reviewer_id=key.reviewer_id,
                    key_id=key.key_id,
                    algorithm=key.algorithm,
                    public_key_base64=key.public_key_base64,
                    status=key.status,
                )
                for key in self.keys
            ),
        )
        if tuple(sorted(self.keys, key=lambda key: (key.reviewer_id, key.key_id))) != self.keys:
            raise ValueError("reviewer keys must be sorted")
        if self.reviewer_trust_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("reviewer trust fingerprint does not match trust declaration")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(
            mode="json",
            exclude={"reviewer_trust_sha256"},
            exclude_none=True,
        )

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def build_reviewer_trust(
    declaration: ReviewerTrustDeclaration,
    policy: ReviewerPolicy,
    *,
    require_active_key_per_reviewer: bool = True,
) -> ReviewerTrust:
    """Normalize declared Ed25519 trust roots and bind them to one review policy."""
    if declaration.benchmark_id != policy.benchmark_id:
        raise ValueError("reviewer trust benchmark_id does not match review policy")
    if declaration.review_policy_sha256 != policy.policy_sha256:
        raise ValueError("reviewer trust policy fingerprint does not match review policy")
    allowed = set(policy.reviewer_ids)
    declared = {key.reviewer_id for key in declaration.keys}
    unauthorized = sorted(declared - allowed)
    if unauthorized:
        raise ValueError(
            "reviewer trust key is not for an allowed reviewer: "
            f"{', '.join(unauthorized)}"
        )
    if require_active_key_per_reviewer:
        active = {key.reviewer_id for key in declaration.keys if key.status == "active"}
        missing = sorted(allowed - active)
        if missing:
            raise ValueError(f"allowed reviewer has no active key: {', '.join(missing)}")
    keys = tuple(
        sorted(
            (
                ReviewerPublicKey(
                    reviewer_id=key.reviewer_id,
                    key_id=key.key_id,
                    algorithm=key.algorithm,
                    public_key_base64=key.public_key_base64,
                    public_key_sha256=hashlib.sha256(
                        _decode_base64(
                            key.public_key_base64,
                            label="public_key_base64",
                            length=32,
                        )
                    ).hexdigest(),
                    status=key.status,
                )
                for key in declaration.keys
            ),
            key=lambda key: (key.reviewer_id, key.key_id),
        )
    )
    payload = {
        "schema_version": declaration.schema_version,
        "benchmark_id": declaration.benchmark_id,
        "review_policy_sha256": declaration.review_policy_sha256,
        "keys": [key.model_dump(mode="json") for key in keys],
    }
    if declaration.reviewer_authority_sha256 is not None:
        payload["reviewer_authority_sha256"] = declaration.reviewer_authority_sha256
    return ReviewerTrust(**payload, reviewer_trust_sha256=_canonical_sha256(payload))


def completed_reviews_sha256(reviews: AdjudicationReviews) -> str:
    """Fingerprint the exact completed review artifact."""
    if reviews.review_completed is not True:
        raise ValueError("review attestations require review_completed=true")
    return _canonical_sha256(reviews.model_dump(mode="json"))


def _reviewer_decisions_sha256(
    decisions: tuple[ReviewDecision, ...],
    reviewer_id: str,
) -> str:
    owned = sorted(
        (
            decision.model_dump(mode="json")
            for decision in decisions
            if decision.reviewer_id == reviewer_id
        ),
        key=lambda decision: (decision["arm"], decision["trial"]),
    )
    if not owned:
        raise ValueError(f"reviewer has no decisions: {reviewer_id}")
    return _canonical_sha256(owned)


class ReviewerAttestationStatement(_FrozenModel):
    schema_version: int
    benchmark_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    preflight_sha256: str = Field(pattern=_SHA256_PATTERN)
    evidence_sha256: str = Field(pattern=_SHA256_PATTERN)
    review_policy_sha256: str = Field(pattern=_SHA256_PATTERN)
    reviewer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    reviews_sha256: str = Field(pattern=_SHA256_PATTERN)
    reviewer_id: str = Field(min_length=1, max_length=200)
    reviewer_decisions_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_statement(self) -> ReviewerAttestationStatement:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.reviewer_id, label="reviewer_id")
        return self

    def signing_bytes(self) -> bytes:
        return _canonical_json(self.model_dump(mode="json")).encode()


class AttestationSigningRequest(_FrozenModel):
    statement: ReviewerAttestationStatement
    signing_payload_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_payload(self) -> AttestationSigningRequest:
        expected = self.statement.signing_bytes()
        try:
            decoded = base64.b64decode(self.signing_payload_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("signing payload must be canonical base64") from exc
        if decoded != expected or base64.b64encode(decoded).decode() != self.signing_payload_base64:
            raise ValueError("signing payload does not match attestation statement")
        return self


class ReviewAttestationTemplate(_FrozenModel):
    schema_version: int
    benchmark_id: str = Field(min_length=1)
    review_policy_sha256: str = Field(pattern=_SHA256_PATTERN)
    reviewer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    reviews_sha256: str = Field(pattern=_SHA256_PATTERN)
    requests: tuple[AttestationSigningRequest, ...] = Field(min_length=1)
    attestations_completed: Literal[False] = False

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class SignedReviewAttestation(_FrozenModel):
    statement: ReviewerAttestationStatement
    key_id: str = Field(min_length=1, max_length=200)
    signature_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_signature_encoding(self) -> SignedReviewAttestation:
        _validate_identifier(self.key_id, label="key_id")
        _decode_base64(self.signature_base64, label="signature_base64", length=64)
        return self


class ReviewAttestationBundle(_FrozenModel):
    schema_version: int
    benchmark_id: str = Field(min_length=1)
    review_policy_sha256: str = Field(pattern=_SHA256_PATTERN)
    reviewer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    reviews_sha256: str = Field(pattern=_SHA256_PATTERN)
    attestations: tuple[SignedReviewAttestation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bundle(self) -> ReviewAttestationBundle:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        reviewer_ids = [item.statement.reviewer_id for item in self.attestations]
        if len(reviewer_ids) != len(set(reviewer_ids)):
            raise ValueError("review attestations must contain one signature per reviewer")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def build_review_attestation_template(
    policy: ReviewerPolicy,
    trust: ReviewerTrust,
    reviews: AdjudicationReviews,
) -> ReviewAttestationTemplate:
    """Create canonical signing payloads without reading or retaining private keys."""
    validate_reviewer_separation(policy, reviews)
    if trust.benchmark_id != reviews.benchmark_id:
        raise ValueError("reviewer trust benchmark_id does not match reviews")
    if trust.review_policy_sha256 != policy.policy_sha256:
        raise ValueError("reviewer trust policy fingerprint does not match review policy")
    if reviews.reviewer_trust_sha256 != trust.reviewer_trust_sha256:
        raise ValueError("reviewer trust fingerprint does not match reviews")
    if reviews.preflight_sha256 is None or reviews.evidence_sha256 is None:
        raise ValueError("attested reviews require preflight and evidence bindings")
    reviews_sha256 = completed_reviews_sha256(reviews)
    reviewer_ids = sorted({decision.reviewer_id for decision in reviews.decisions})
    requests = []
    for reviewer_id in reviewer_ids:
        statement = ReviewerAttestationStatement(
            schema_version=SCHEMA_VERSION,
            benchmark_id=reviews.benchmark_id,
            task_id=reviews.task_id,
            workspace_revision=reviews.workspace_revision,
            preflight_sha256=reviews.preflight_sha256,
            evidence_sha256=reviews.evidence_sha256,
            review_policy_sha256=policy.policy_sha256,
            reviewer_trust_sha256=trust.reviewer_trust_sha256,
            reviews_sha256=reviews_sha256,
            reviewer_id=reviewer_id,
            reviewer_decisions_sha256=_reviewer_decisions_sha256(
                reviews.decisions,
                reviewer_id,
            ),
        )
        requests.append(
            AttestationSigningRequest(
                statement=statement,
                signing_payload_base64=base64.b64encode(statement.signing_bytes()).decode(),
            )
        )
    return ReviewAttestationTemplate(
        schema_version=SCHEMA_VERSION,
        benchmark_id=reviews.benchmark_id,
        review_policy_sha256=policy.policy_sha256,
        reviewer_trust_sha256=trust.reviewer_trust_sha256,
        reviews_sha256=reviews_sha256,
        requests=tuple(requests),
    )


def verify_review_attestations(
    policy: ReviewerPolicy,
    trust: ReviewerTrust,
    reviews: AdjudicationReviews,
    bundle: ReviewAttestationBundle,
) -> None:
    """Verify complete reviewer coverage and every detached Ed25519 signature."""
    expected = build_review_attestation_template(policy, trust, reviews)
    if bundle.benchmark_id != expected.benchmark_id:
        raise ValueError("attestation benchmark_id does not match reviews")
    if bundle.review_policy_sha256 != expected.review_policy_sha256:
        raise ValueError("attestation policy fingerprint does not match reviews")
    if bundle.reviewer_trust_sha256 != expected.reviewer_trust_sha256:
        raise ValueError("attestation trust fingerprint does not match reviews")
    if bundle.reviews_sha256 != expected.reviews_sha256:
        raise ValueError("attestation reviews fingerprint does not match reviews")
    signed_by_reviewer = {
        attestation.statement.reviewer_id: attestation
        for attestation in bundle.attestations
    }
    expected_by_reviewer = {
        request.statement.reviewer_id: request.statement for request in expected.requests
    }
    if set(signed_by_reviewer) != set(expected_by_reviewer):
        raise ValueError("attestation reviewer coverage does not match completed reviews")
    keys = {(key.reviewer_id, key.key_id): key for key in trust.keys}
    for reviewer_id, statement in expected_by_reviewer.items():
        attestation = signed_by_reviewer[reviewer_id]
        if attestation.statement != statement:
            raise ValueError(f"attestation statement does not match reviews: {reviewer_id}")
        key = keys.get((reviewer_id, attestation.key_id))
        if key is None:
            raise ValueError(f"attestation signing key is not trusted: {reviewer_id}")
        if key.status != "active":
            raise ValueError(f"attestation signing key is revoked: {reviewer_id}")
        try:
            Ed25519PublicKey.from_public_bytes(
                _decode_base64(
                    key.public_key_base64,
                    label="public_key_base64",
                    length=32,
                )
            ).verify(
                _decode_base64(
                    attestation.signature_base64,
                    label="signature_base64",
                    length=64,
                ),
                statement.signing_bytes(),
            )
        except (InvalidSignature, ValueError) as exc:
            raise ValueError(f"attestation signature is invalid: {reviewer_id}") from exc

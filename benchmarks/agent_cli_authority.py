"""Offline organization authority for reviewer enrollment and campaign envelopes."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.agent_cli_adjudication import (
    AdjudicationReviews,
    RecordedEvidence,
    finalize_recorded_results,
)
from benchmarks.agent_cli_attestation import (
    ReviewAttestationBundle,
    ReviewerPublicKey,
    ReviewerTrust,
    completed_reviews_sha256,
)
from benchmarks.agent_cli_comparison import (
    SCHEMA_VERSION,
    AgentCliManifest,
    RecordedResults,
)
from benchmarks.agent_cli_preflight import CampaignPreflight, validate_review_bindings
from benchmarks.agent_cli_review_policy import ReviewerPolicy

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


def _model_sha256(model: BaseModel) -> str:
    return _canonical_sha256(model.model_dump(mode="json"))


def _decode_base64(value: str, *, label: str, length: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{label} must be canonical base64") from exc
    if len(decoded) != length or base64.b64encode(decoded).decode() != value:
        raise ValueError(f"{label} must encode exactly {length} bytes")
    return decoded


def _validate_identifier(identifier: str, *, label: str) -> None:
    if not identifier or identifier != identifier.strip():
        raise ValueError(f"{label} must be non-blank without surrounding whitespace")


class BenchmarkAuthorityDeclaration(_FrozenModel):
    schema_version: int
    authority_id: str = Field(min_length=1, max_length=200)
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_declaration(self) -> BenchmarkAuthorityDeclaration:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.authority_id, label="authority_id")
        _decode_base64(self.public_key_base64, label="public_key_base64", length=32)
        return self


class BenchmarkAuthority(_FrozenModel):
    schema_version: int
    authority_id: str = Field(min_length=1, max_length=200)
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: str = Field(min_length=1)
    public_key_sha256: str = Field(pattern=_SHA256_PATTERN)
    authority_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_fingerprints(self) -> BenchmarkAuthority:
        BenchmarkAuthorityDeclaration(
            schema_version=self.schema_version,
            authority_id=self.authority_id,
            algorithm=self.algorithm,
            public_key_base64=self.public_key_base64,
        )
        public_key = _decode_base64(
            self.public_key_base64,
            label="public_key_base64",
            length=32,
        )
        if self.public_key_sha256 != hashlib.sha256(public_key).hexdigest():
            raise ValueError("authority public key fingerprint does not match key")
        if self.authority_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("authority fingerprint does not match declaration")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"authority_sha256"})

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def build_benchmark_authority(
    declaration: BenchmarkAuthorityDeclaration,
) -> BenchmarkAuthority:
    """Normalize one out-of-band organization authority public key."""
    public_key = _decode_base64(
        declaration.public_key_base64,
        label="public_key_base64",
        length=32,
    )
    payload = {
        **declaration.model_dump(mode="json"),
        "public_key_sha256": hashlib.sha256(public_key).hexdigest(),
    }
    return BenchmarkAuthority(**payload, authority_sha256=_canonical_sha256(payload))


class ReviewerEnrollmentStatement(_FrozenModel):
    schema_version: int
    authority_sha256: str = Field(pattern=_SHA256_PATTERN)
    benchmark_id: str = Field(min_length=1)
    review_policy_sha256: str = Field(pattern=_SHA256_PATTERN)
    reviewer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    reviewer_id: str = Field(min_length=1, max_length=200)
    key_id: str = Field(min_length=1, max_length=200)
    algorithm: Literal["ed25519"] = "ed25519"
    reviewer_public_key_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_statement(self) -> ReviewerEnrollmentStatement:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.reviewer_id, label="reviewer_id")
        _validate_identifier(self.key_id, label="key_id")
        return self

    def signing_bytes(self) -> bytes:
        return _canonical_json(self.model_dump(mode="json")).encode()


class ReviewerEnrollmentSigningRequest(_FrozenModel):
    statement: ReviewerEnrollmentStatement
    signing_payload_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_payload(self) -> ReviewerEnrollmentSigningRequest:
        expected = self.statement.signing_bytes()
        try:
            decoded = base64.b64decode(self.signing_payload_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("reviewer enrollment payload must be canonical base64") from exc
        if decoded != expected or base64.b64encode(decoded).decode() != self.signing_payload_base64:
            raise ValueError("reviewer enrollment payload does not match statement")
        return self


class ReviewerEnrollmentTemplate(_FrozenModel):
    schema_version: int
    authority_sha256: str = Field(pattern=_SHA256_PATTERN)
    benchmark_id: str = Field(min_length=1)
    review_policy_sha256: str = Field(pattern=_SHA256_PATTERN)
    reviewer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    requests: tuple[ReviewerEnrollmentSigningRequest, ...] = Field(min_length=1)
    enrollments_completed: Literal[False] = False

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class ReviewerEnrollmentCertificate(_FrozenModel):
    statement: ReviewerEnrollmentStatement
    signature_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_signature_encoding(self) -> ReviewerEnrollmentCertificate:
        _decode_base64(self.signature_base64, label="signature_base64", length=64)
        return self


class ReviewerEnrollmentBundle(_FrozenModel):
    schema_version: int
    authority_sha256: str = Field(pattern=_SHA256_PATTERN)
    benchmark_id: str = Field(min_length=1)
    review_policy_sha256: str = Field(pattern=_SHA256_PATTERN)
    reviewer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    certificates: tuple[ReviewerEnrollmentCertificate, ...] = Field(min_length=1)
    reviewer_enrollments_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_bundle(self) -> ReviewerEnrollmentBundle:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        identities = [
            (certificate.statement.reviewer_id, certificate.statement.key_id)
            for certificate in self.certificates
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("reviewer enrollment certificates must be unique")
        if tuple(sorted(self.certificates, key=_certificate_identity)) != self.certificates:
            raise ValueError("reviewer enrollment certificates must be sorted")
        if self.reviewer_enrollments_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("reviewer enrollment fingerprint does not match bundle")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"reviewer_enrollments_sha256"})

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _certificate_identity(
    certificate: ReviewerEnrollmentCertificate,
) -> tuple[str, str]:
    return certificate.statement.reviewer_id, certificate.statement.key_id


def build_reviewer_enrollment_statement(
    authority: BenchmarkAuthority,
    policy: ReviewerPolicy,
    trust: ReviewerTrust,
    key: ReviewerPublicKey,
) -> ReviewerEnrollmentStatement:
    """Bind one reviewer public key to the authority, policy, and exact trust artifact."""
    if trust.reviewer_authority_sha256 != authority.authority_sha256:
        raise ValueError("reviewer trust authority fingerprint does not match authority")
    if trust.benchmark_id != policy.benchmark_id:
        raise ValueError("reviewer trust benchmark_id does not match review policy")
    if trust.review_policy_sha256 != policy.policy_sha256:
        raise ValueError("reviewer trust policy fingerprint does not match review policy")
    if key not in trust.keys:
        raise ValueError("reviewer key is not present in trust")
    return ReviewerEnrollmentStatement(
        schema_version=SCHEMA_VERSION,
        authority_sha256=authority.authority_sha256,
        benchmark_id=trust.benchmark_id,
        review_policy_sha256=policy.policy_sha256,
        reviewer_trust_sha256=trust.reviewer_trust_sha256,
        reviewer_id=key.reviewer_id,
        key_id=key.key_id,
        algorithm=key.algorithm,
        reviewer_public_key_sha256=key.public_key_sha256,
    )


def build_reviewer_enrollment_template(
    authority: BenchmarkAuthority,
    policy: ReviewerPolicy,
    trust: ReviewerTrust,
) -> ReviewerEnrollmentTemplate:
    """Create authority signing payloads for every key without reading a private key."""
    requests = []
    for key in trust.keys:
        statement = build_reviewer_enrollment_statement(
            authority,
            policy,
            trust,
            key,
        )
        requests.append(
            ReviewerEnrollmentSigningRequest(
                statement=statement,
                signing_payload_base64=base64.b64encode(statement.signing_bytes()).decode(),
            )
        )
    return ReviewerEnrollmentTemplate(
        schema_version=SCHEMA_VERSION,
        authority_sha256=authority.authority_sha256,
        benchmark_id=trust.benchmark_id,
        review_policy_sha256=policy.policy_sha256,
        reviewer_trust_sha256=trust.reviewer_trust_sha256,
        requests=tuple(requests),
    )


def build_reviewer_enrollment_bundle(
    authority: BenchmarkAuthority,
    policy: ReviewerPolicy,
    trust: ReviewerTrust,
    certificates: tuple[ReviewerEnrollmentCertificate, ...],
) -> ReviewerEnrollmentBundle:
    """Normalize and verify organization-signed reviewer key enrollments."""
    ordered = tuple(sorted(certificates, key=_certificate_identity))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "authority_sha256": authority.authority_sha256,
        "benchmark_id": trust.benchmark_id,
        "review_policy_sha256": policy.policy_sha256,
        "reviewer_trust_sha256": trust.reviewer_trust_sha256,
        "certificates": [certificate.model_dump(mode="json") for certificate in ordered],
    }
    bundle = ReviewerEnrollmentBundle(
        **payload,
        reviewer_enrollments_sha256=_canonical_sha256(payload),
    )
    verify_reviewer_enrollments(authority, policy, trust, bundle)
    return bundle


def verify_reviewer_enrollments(
    authority: BenchmarkAuthority,
    policy: ReviewerPolicy,
    trust: ReviewerTrust,
    bundle: ReviewerEnrollmentBundle,
) -> None:
    """Require an authority signature for every key in the exact reviewer trust."""
    if bundle.reviewer_enrollments_sha256 != _canonical_sha256(
        bundle._binding_payload()
    ):
        raise ValueError("reviewer enrollment fingerprint does not match bundle")
    if trust.reviewer_authority_sha256 != authority.authority_sha256:
        raise ValueError("reviewer trust authority fingerprint does not match authority")
    expected_headers = (
        authority.authority_sha256,
        trust.benchmark_id,
        policy.policy_sha256,
        trust.reviewer_trust_sha256,
    )
    actual_headers = (
        bundle.authority_sha256,
        bundle.benchmark_id,
        bundle.review_policy_sha256,
        bundle.reviewer_trust_sha256,
    )
    if actual_headers != expected_headers:
        raise ValueError("reviewer enrollment trust fingerprint does not match campaign")
    certificates = {_certificate_identity(item): item for item in bundle.certificates}
    keys = {(key.reviewer_id, key.key_id): key for key in trust.keys}
    if set(certificates) != set(keys):
        raise ValueError("reviewer enrollment certificate coverage does not match trust")
    public_key = Ed25519PublicKey.from_public_bytes(
        _decode_base64(
            authority.public_key_base64,
            label="public_key_base64",
            length=32,
        )
    )
    for identity, key in keys.items():
        certificate = certificates[identity]
        expected_statement = build_reviewer_enrollment_statement(
            authority,
            policy,
            trust,
            key,
        )
        if certificate.statement != expected_statement:
            raise ValueError(f"reviewer enrollment statement does not match trust: {key.key_id}")
        try:
            public_key.verify(
                _decode_base64(
                    certificate.signature_base64,
                    label="signature_base64",
                    length=64,
                ),
                certificate.statement.signing_bytes(),
            )
        except (InvalidSignature, ValueError) as exc:
            raise ValueError(f"reviewer enrollment signature is invalid: {key.key_id}") from exc


class CampaignEnvelopeStatement(_FrozenModel):
    schema_version: int
    authority_sha256: str = Field(pattern=_SHA256_PATTERN)
    benchmark_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    preflight_sha256: str = Field(pattern=_SHA256_PATTERN)
    evidence_sha256: str = Field(pattern=_SHA256_PATTERN)
    reviews_sha256: str = Field(pattern=_SHA256_PATTERN)
    review_policy_sha256: str = Field(pattern=_SHA256_PATTERN)
    reviewer_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    reviewer_enrollments_sha256: str = Field(pattern=_SHA256_PATTERN)
    attestations_sha256: str = Field(pattern=_SHA256_PATTERN)
    results_sha256: str = Field(pattern=_SHA256_PATTERN)
    paid_execution_authorized: Literal[False] = False
    envelope_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_statement(self) -> CampaignEnvelopeStatement:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        expected = _canonical_sha256(
            self.model_dump(mode="json", exclude={"envelope_sha256"})
        )
        if self.envelope_sha256 != expected:
            raise ValueError("campaign envelope fingerprint does not match artifacts")
        return self

    def signing_bytes(self) -> bytes:
        return _canonical_json(self.model_dump(mode="json")).encode()


class CampaignEnvelopeSigningRequest(_FrozenModel):
    statement: CampaignEnvelopeStatement
    signing_payload_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_payload(self) -> CampaignEnvelopeSigningRequest:
        expected = self.statement.signing_bytes()
        try:
            decoded = base64.b64decode(self.signing_payload_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("campaign envelope payload must be canonical base64") from exc
        if decoded != expected or base64.b64encode(decoded).decode() != self.signing_payload_base64:
            raise ValueError("campaign envelope payload does not match statement")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class SignedCampaignEnvelope(_FrozenModel):
    statement: CampaignEnvelopeStatement
    signature_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_signature_encoding(self) -> SignedCampaignEnvelope:
        _decode_base64(self.signature_base64, label="signature_base64", length=64)
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _validate_manifest_preflight(
    manifest: AgentCliManifest,
    preflight: CampaignPreflight,
) -> None:
    identity = (manifest.benchmark_id, manifest.task.id, manifest.task.workspace_revision)
    if (preflight.benchmark_id, preflight.task_id, preflight.workspace_revision) != identity:
        raise ValueError("preflight identity does not match manifest")
    if preflight.manifest_sha256 != _model_sha256(manifest):
        raise ValueError("preflight manifest fingerprint does not match manifest")


def build_campaign_envelope_request(
    *,
    authority: BenchmarkAuthority,
    manifest: AgentCliManifest,
    preflight: CampaignPreflight,
    evidence: RecordedEvidence,
    reviews: AdjudicationReviews,
    review_policy: ReviewerPolicy,
    reviewer_trust: ReviewerTrust,
    reviewer_enrollments: ReviewerEnrollmentBundle,
    attestations: ReviewAttestationBundle,
    results: RecordedResults,
) -> CampaignEnvelopeSigningRequest:
    """Bind a validated campaign into one non-authorizing authority signing payload."""
    _validate_manifest_preflight(manifest, preflight)
    validate_review_bindings(preflight, evidence, reviews)
    verify_reviewer_enrollments(
        authority,
        review_policy,
        reviewer_trust,
        reviewer_enrollments,
    )
    expected_results = finalize_recorded_results(
        manifest,
        evidence,
        reviews,
        review_policy=review_policy,
        reviewer_trust=reviewer_trust,
        attestations=attestations,
        reviewer_authority=authority,
        reviewer_enrollments=reviewer_enrollments,
    )
    if results != expected_results:
        raise ValueError("results do not match authority-anchored campaign artifacts")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "authority_sha256": authority.authority_sha256,
        "benchmark_id": manifest.benchmark_id,
        "task_id": manifest.task.id,
        "workspace_revision": manifest.task.workspace_revision,
        "manifest_sha256": _model_sha256(manifest),
        "preflight_sha256": preflight.preflight_sha256,
        "evidence_sha256": _model_sha256(evidence),
        "reviews_sha256": completed_reviews_sha256(reviews),
        "review_policy_sha256": review_policy.policy_sha256,
        "reviewer_trust_sha256": reviewer_trust.reviewer_trust_sha256,
        "reviewer_enrollments_sha256": (
            reviewer_enrollments.reviewer_enrollments_sha256
        ),
        "attestations_sha256": _model_sha256(attestations),
        "results_sha256": _model_sha256(results),
        "paid_execution_authorized": False,
    }
    statement = CampaignEnvelopeStatement(
        **payload,
        envelope_sha256=_canonical_sha256(payload),
    )
    return CampaignEnvelopeSigningRequest(
        statement=statement,
        signing_payload_base64=base64.b64encode(statement.signing_bytes()).decode(),
    )


def verify_signed_campaign_envelope(
    *,
    authority: BenchmarkAuthority,
    manifest: AgentCliManifest,
    preflight: CampaignPreflight,
    evidence: RecordedEvidence,
    reviews: AdjudicationReviews,
    review_policy: ReviewerPolicy,
    reviewer_trust: ReviewerTrust,
    reviewer_enrollments: ReviewerEnrollmentBundle,
    attestations: ReviewAttestationBundle,
    results: RecordedResults,
    envelope: SignedCampaignEnvelope,
) -> None:
    """Verify the authority signature over the complete finalized campaign chain."""
    expected = build_campaign_envelope_request(
        authority=authority,
        manifest=manifest,
        preflight=preflight,
        evidence=evidence,
        reviews=reviews,
        review_policy=review_policy,
        reviewer_trust=reviewer_trust,
        reviewer_enrollments=reviewer_enrollments,
        attestations=attestations,
        results=results,
    )
    if envelope.statement != expected.statement:
        raise ValueError("signed campaign envelope does not match campaign artifacts")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode_base64(
                authority.public_key_base64,
                label="public_key_base64",
                length=32,
            )
        ).verify(
            _decode_base64(
                envelope.signature_base64,
                label="signature_base64",
                length=64,
            ),
            envelope.statement.signing_bytes(),
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("campaign envelope signature is invalid") from exc

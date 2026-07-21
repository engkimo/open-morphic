"""Read-only lifecycle status for recorded agent CLI benchmark campaigns."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from benchmarks.agent_cli_adjudication import (
    AdjudicationReviews,
    RecordedEvidence,
    finalize_recorded_results,
    recorded_evidence_sha256,
)
from benchmarks.agent_cli_attestation import (
    ReviewAttestationBundle,
    ReviewerTrust,
    verify_review_attestations,
)
from benchmarks.agent_cli_authority import (
    BenchmarkAuthority,
    ReviewerEnrollmentBundle,
    SignedCampaignEnvelope,
    verify_reviewer_enrollments,
    verify_signed_campaign_envelope,
)
from benchmarks.agent_cli_comparison import (
    SCHEMA_VERSION,
    AgentCliManifest,
    RecordedResults,
)
from benchmarks.agent_cli_preflight import (
    CampaignPreflight,
    ReviewTemplate,
    build_review_template,
    validate_review_bindings,
)
from benchmarks.agent_cli_review_policy import (
    ReviewerPolicy,
    validate_reviewer_policy_capacity,
    validate_reviewer_separation,
)
from benchmarks.agent_cli_transparency import (
    SignedAuthorityRootLedger,
    TransparencyInclusionProof,
    verify_authority_root_ledger,
    verify_transparency_inclusion_proof,
)


class CampaignStage(str, Enum):
    MANIFEST_READY = "manifest_ready"
    PREFLIGHT_READY = "preflight_ready"
    RECORDED = "recorded"
    REVIEW_PENDING = "review_pending"
    AUTHORITY_ROOT_PENDING = "authority_root_pending"
    REVIEWER_ENROLLMENT_PENDING = "reviewer_enrollment_pending"
    REVIEW_ATTESTATION_PENDING = "review_attestation_pending"
    REVIEW_COMPLETE = "review_complete"
    CAMPAIGN_ENVELOPE_PENDING = "campaign_envelope_pending"
    TRANSPARENCY_PENDING = "transparency_pending"
    FINALIZED = "finalized"


class CampaignStatus(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid", frozen=True)

    schema_version: int
    benchmark_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    workspace_revision: str = Field(min_length=1)
    stage: CampaignStage
    has_preflight: bool
    has_evidence: bool
    has_review: bool
    has_reviewer_enrollments: bool
    has_attestations: bool
    has_results: bool
    has_campaign_envelope: bool
    has_authority_root_ledger: bool
    has_transparency_proof: bool
    preflight_sha256: str | None = None
    evidence_sha256: str | None = None
    review_policy_sha256: str | None = None
    reviewer_trust_sha256: str | None = None
    reviewer_authority_sha256: str | None = None
    authority_root_ledger_sha256: str | None = None
    reviewer_enrollments_sha256: str | None = None
    attestations_verified: bool
    campaign_envelope_verified: bool
    authority_root_ledger_verified: bool
    transparency_inclusion_verified: bool
    paid_execution_authorized: Literal[False] = False
    next_action: str = Field(min_length=1)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _validate_preflight_manifest(
    manifest: AgentCliManifest,
    preflight: CampaignPreflight,
) -> None:
    identity = (manifest.benchmark_id, manifest.task.id, manifest.task.workspace_revision)
    if (
        preflight.benchmark_id,
        preflight.task_id,
        preflight.workspace_revision,
    ) != identity:
        raise ValueError("preflight identity does not match manifest")
    manifest_body = json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if preflight.manifest_sha256 != hashlib.sha256(manifest_body.encode()).hexdigest():
        raise ValueError("preflight manifest fingerprint does not match manifest")


def _validate_template(
    preflight: CampaignPreflight,
    evidence: RecordedEvidence,
    template: ReviewTemplate,
    policy: ReviewerPolicy | None,
    trust: ReviewerTrust | None,
) -> None:
    if policy is not None:
        validate_reviewer_policy_capacity(policy, decision_count=len(template.decisions))
    if trust is not None and policy is None:
        raise ValueError("review policy is required with reviewer trust")
    if trust is not None and policy is not None:
        if trust.benchmark_id != policy.benchmark_id:
            raise ValueError("reviewer trust benchmark_id does not match review policy")
        if trust.review_policy_sha256 != policy.policy_sha256:
            raise ValueError("reviewer trust policy fingerprint does not match review policy")
    expected = build_review_template(
        preflight,
        evidence,
        review_policy_sha256=(policy.policy_sha256 if policy is not None else None),
        reviewer_trust_sha256=(
            trust.reviewer_trust_sha256 if trust is not None else None
        ),
    )
    if template != expected:
        raise ValueError("review template does not match campaign artifacts")


def build_campaign_status(
    manifest: AgentCliManifest,
    *,
    preflight: CampaignPreflight | None = None,
    evidence: RecordedEvidence | None = None,
    review_template: ReviewTemplate | None = None,
    reviews: AdjudicationReviews | None = None,
    results: RecordedResults | None = None,
    review_policy: ReviewerPolicy | None = None,
    reviewer_trust: ReviewerTrust | None = None,
    attestations: ReviewAttestationBundle | None = None,
    reviewer_authority: BenchmarkAuthority | None = None,
    reviewer_enrollments: ReviewerEnrollmentBundle | None = None,
    campaign_envelope: SignedCampaignEnvelope | None = None,
    authority_root_ledger: SignedAuthorityRootLedger | None = None,
    transparency_proof: TransparencyInclusionProof | None = None,
) -> CampaignStatus:
    """Validate supplied artifacts and report the furthest complete lifecycle stage."""
    if evidence is not None and preflight is None:
        raise ValueError("preflight is required before evidence")
    if (review_template is not None or reviews is not None) and evidence is None:
        raise ValueError("evidence is required before review")
    if review_template is not None and reviews is not None:
        raise ValueError("provide pending review template or completed reviews, not both")
    if results is not None and reviews is None:
        raise ValueError("completed reviews are required before results")
    if attestations is not None and reviews is None:
        raise ValueError("completed reviews are required before attestations")
    if reviewer_enrollments is not None and reviewer_authority is None:
        raise ValueError("reviewer authority is required before reviewer enrollments")
    if campaign_envelope is not None and results is None:
        raise ValueError("results are required before a signed campaign envelope")
    if authority_root_ledger is not None and reviewer_authority is None:
        raise ValueError("reviewer authority is required with an authority root ledger")
    if transparency_proof is not None and campaign_envelope is None:
        raise ValueError("signed campaign envelope is required before transparency proof")
    if transparency_proof is not None and authority_root_ledger is None:
        raise ValueError("authority root ledger is required before transparency proof")

    stage = CampaignStage.MANIFEST_READY
    next_action = "create_preflight"
    attestations_verified = False
    campaign_envelope_verified = False
    authority_root_ledger_verified = False
    transparency_inclusion_verified = False
    if preflight is not None:
        _validate_preflight_manifest(manifest, preflight)
        stage = CampaignStage.PREFLIGHT_READY
        next_action = "record_trials_with_explicit_consent"
    if evidence is not None:
        assert preflight is not None
        if evidence.estimated_max_cost_usd != preflight.estimated_max_cost_usd:
            raise ValueError("evidence estimate does not match preflight")
        build_review_template(preflight, evidence)
        stage = CampaignStage.RECORDED
        next_action = "create_review_template"
    if review_template is not None:
        assert preflight is not None and evidence is not None
        _validate_template(
            preflight,
            evidence,
            review_template,
            review_policy,
            reviewer_trust,
        )
        stage = CampaignStage.REVIEW_PENDING
        next_action = "complete_independent_review"
    if reviews is not None:
        assert preflight is not None and evidence is not None
        validate_review_bindings(preflight, evidence, reviews)
        if review_policy is not None:
            validate_reviewer_separation(review_policy, reviews)
        elif reviews.review_policy_sha256 is not None:
            raise ValueError("review policy is required for policy-bound reviews")
        if reviews.reviewer_trust_sha256 is not None:
            if reviewer_trust is None:
                raise ValueError("reviewer trust is required for trust-bound reviews")
            authority_bound = reviewer_trust.reviewer_authority_sha256 is not None
            enrollments_verified = not authority_bound
            if authority_bound:
                if (
                    reviewer_authority is not None
                    and reviewer_trust.reviewer_authority_sha256
                    != reviewer_authority.authority_sha256
                ):
                    raise ValueError(
                        "reviewer trust authority fingerprint does not match authority"
                    )
                ledger_bound = reviewer_trust.authority_root_ledger_sha256 is not None
                root_ready = True
                if ledger_bound and authority_root_ledger is None:
                    stage = CampaignStage.AUTHORITY_ROOT_PENDING
                    next_action = "provide_authority_root_ledger"
                    root_ready = False
                elif ledger_bound:
                    assert authority_root_ledger is not None
                    active = verify_authority_root_ledger(authority_root_ledger)
                    if active != reviewer_authority:
                        raise ValueError("reviewer authority is not the active authority root")
                    if (
                        authority_root_ledger.statement.ledger_sha256
                        != reviewer_trust.authority_root_ledger_sha256
                    ):
                        raise ValueError(
                            "reviewer trust authority root ledger does not match ledger"
                        )
                    authority_root_ledger_verified = True
                elif authority_root_ledger is not None:
                    raise ValueError("authority root ledger requires ledger-bound trust")
                if root_ready and (
                    reviewer_authority is None or reviewer_enrollments is None
                ):
                    stage = CampaignStage.REVIEWER_ENROLLMENT_PENDING
                    next_action = "collect_authority_enrollments"
                elif root_ready:
                    assert review_policy is not None
                    verify_reviewer_enrollments(
                        reviewer_authority,
                        review_policy,
                        reviewer_trust,
                        reviewer_enrollments,
                    )
                    enrollments_verified = True
            elif reviewer_authority is not None or reviewer_enrollments is not None:
                raise ValueError("reviewer enrollments require an authority-bound trust")
            if enrollments_verified and attestations is None:
                stage = CampaignStage.REVIEW_ATTESTATION_PENDING
                next_action = "collect_reviewer_attestations"
            elif enrollments_verified:
                assert review_policy is not None
                verify_review_attestations(
                    review_policy,
                    reviewer_trust,
                    reviews,
                    attestations,
                )
                attestations_verified = True
                stage = CampaignStage.REVIEW_COMPLETE
                next_action = "finalize_results"
        else:
            if reviewer_trust is not None or attestations is not None:
                raise ValueError("attestations require a reviewer trust binding")
            stage = CampaignStage.REVIEW_COMPLETE
            next_action = "finalize_results"
    if results is not None:
        assert evidence is not None and reviews is not None
        expected_results = finalize_recorded_results(
            manifest,
            evidence,
            reviews,
            review_policy=review_policy,
            reviewer_trust=reviewer_trust,
            attestations=attestations,
            reviewer_authority=reviewer_authority,
            reviewer_enrollments=reviewer_enrollments,
            authority_root_ledger=authority_root_ledger,
        )
        if results != expected_results:
            raise ValueError("results do not match finalized campaign artifacts")
        if (
            reviewer_trust is not None
            and reviewer_trust.reviewer_authority_sha256 is not None
        ):
            assert preflight is not None
            assert review_policy is not None
            assert reviewer_authority is not None
            assert reviewer_enrollments is not None
            assert attestations is not None
            if campaign_envelope is None:
                stage = CampaignStage.CAMPAIGN_ENVELOPE_PENDING
                next_action = "sign_campaign_envelope"
            else:
                verify_signed_campaign_envelope(
                    authority=reviewer_authority,
                    manifest=manifest,
                    preflight=preflight,
                    evidence=evidence,
                    reviews=reviews,
                    review_policy=review_policy,
                    reviewer_trust=reviewer_trust,
                    reviewer_enrollments=reviewer_enrollments,
                    attestations=attestations,
                    results=results,
                    envelope=campaign_envelope,
                    authority_root_ledger=authority_root_ledger,
                )
                campaign_envelope_verified = True
                if reviewer_trust.authority_root_ledger_sha256 is not None:
                    assert authority_root_ledger is not None
                    if transparency_proof is None:
                        stage = CampaignStage.TRANSPARENCY_PENDING
                        next_action = "publish_campaign_envelope_to_transparency_log"
                    else:
                        verify_transparency_inclusion_proof(
                            transparency_proof,
                            authority_root_ledger,
                            expected_kind="campaign_envelope",
                            expected_artifact_sha256=(
                                campaign_envelope.statement.envelope_sha256
                            ),
                        )
                        transparency_inclusion_verified = True
                        stage = CampaignStage.FINALIZED
                        next_action = "campaign_complete"
                else:
                    if transparency_proof is not None:
                        raise ValueError(
                            "transparency proof requires ledger-bound trust"
                        )
                    stage = CampaignStage.FINALIZED
                    next_action = "campaign_complete"
        else:
            if campaign_envelope is not None:
                raise ValueError("campaign envelope requires an authority-bound trust")
            stage = CampaignStage.FINALIZED
            next_action = "campaign_complete"

    return CampaignStatus(
        schema_version=SCHEMA_VERSION,
        benchmark_id=manifest.benchmark_id,
        task_id=manifest.task.id,
        workspace_revision=manifest.task.workspace_revision,
        stage=stage,
        has_preflight=preflight is not None,
        has_evidence=evidence is not None,
        has_review=review_template is not None or reviews is not None,
        has_reviewer_enrollments=reviewer_enrollments is not None,
        has_attestations=attestations is not None,
        has_results=results is not None,
        has_campaign_envelope=campaign_envelope is not None,
        has_authority_root_ledger=authority_root_ledger is not None,
        has_transparency_proof=transparency_proof is not None,
        preflight_sha256=(preflight.preflight_sha256 if preflight is not None else None),
        evidence_sha256=(
            recorded_evidence_sha256(evidence) if evidence is not None else None
        ),
        review_policy_sha256=(
            review_policy.policy_sha256 if review_policy is not None else None
        ),
        reviewer_trust_sha256=(
            reviewer_trust.reviewer_trust_sha256
            if reviewer_trust is not None
            else None
        ),
        reviewer_authority_sha256=(
            reviewer_authority.authority_sha256
            if reviewer_authority is not None
            else None
        ),
        authority_root_ledger_sha256=(
            authority_root_ledger.statement.ledger_sha256
            if authority_root_ledger is not None
            else None
        ),
        reviewer_enrollments_sha256=(
            reviewer_enrollments.reviewer_enrollments_sha256
            if reviewer_enrollments is not None
            else None
        ),
        attestations_verified=attestations_verified,
        campaign_envelope_verified=campaign_envelope_verified,
        authority_root_ledger_verified=authority_root_ledger_verified,
        transparency_inclusion_verified=transparency_inclusion_verified,
        next_action=next_action,
    )

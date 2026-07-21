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


class CampaignStage(str, Enum):
    MANIFEST_READY = "manifest_ready"
    PREFLIGHT_READY = "preflight_ready"
    RECORDED = "recorded"
    REVIEW_PENDING = "review_pending"
    REVIEW_ATTESTATION_PENDING = "review_attestation_pending"
    REVIEW_COMPLETE = "review_complete"
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
    has_attestations: bool
    has_results: bool
    preflight_sha256: str | None = None
    evidence_sha256: str | None = None
    review_policy_sha256: str | None = None
    reviewer_trust_sha256: str | None = None
    attestations_verified: bool
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

    stage = CampaignStage.MANIFEST_READY
    next_action = "create_preflight"
    attestations_verified = False
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
            if attestations is None:
                stage = CampaignStage.REVIEW_ATTESTATION_PENDING
                next_action = "collect_reviewer_attestations"
            else:
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
        )
        if results != expected_results:
            raise ValueError("results do not match finalized campaign artifacts")
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
        has_attestations=attestations is not None,
        has_results=results is not None,
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
        attestations_verified=attestations_verified,
        next_action=next_action,
    )

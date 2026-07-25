"""Structural reviewer separation policy for recorded benchmark campaigns."""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.agent_cli_adjudication import AdjudicationReviews
from benchmarks.agent_cli_comparison import SCHEMA_VERSION

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid", frozen=True)


def _validate_identifier(identifier: str, *, label: str) -> None:
    if identifier != identifier.strip() or not identifier:
        raise ValueError(f"{label} must be non-blank without surrounding whitespace")


class ReviewerPolicyDeclaration(_FrozenModel):
    schema_version: int
    benchmark_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1, max_length=200)
    reviewer_ids: tuple[str, ...] = Field(min_length=1)
    minimum_distinct_reviewers: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_contract(self) -> ReviewerPolicyDeclaration:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.operator_id, label="operator_id")
        for reviewer_id in self.reviewer_ids:
            _validate_identifier(reviewer_id, label="reviewer_id")
        if len(set(self.reviewer_ids)) != len(self.reviewer_ids):
            raise ValueError("reviewer_ids must be unique")
        if self.operator_id in self.reviewer_ids:
            raise ValueError("operator must not be an allowed reviewer")
        if self.minimum_distinct_reviewers > len(self.reviewer_ids):
            raise ValueError("minimum distinct reviewers exceeds allowed reviewers")
        return self


class ReviewerPolicy(_FrozenModel):
    schema_version: int
    benchmark_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1, max_length=200)
    reviewer_ids: tuple[str, ...] = Field(min_length=1)
    minimum_distinct_reviewers: int = Field(ge=1)
    policy_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_fingerprint(self) -> ReviewerPolicy:
        declaration = ReviewerPolicyDeclaration(
            schema_version=self.schema_version,
            benchmark_id=self.benchmark_id,
            operator_id=self.operator_id,
            reviewer_ids=self.reviewer_ids,
            minimum_distinct_reviewers=self.minimum_distinct_reviewers,
        )
        if tuple(sorted(declaration.reviewer_ids)) != self.reviewer_ids:
            raise ValueError("reviewer_ids must be sorted")
        expected = _policy_sha256(declaration)
        if self.policy_sha256 != expected:
            raise ValueError("review policy fingerprint does not match policy")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _policy_sha256(declaration: ReviewerPolicyDeclaration) -> str:
    payload = declaration.model_dump(mode="json")
    payload["reviewer_ids"] = sorted(payload["reviewer_ids"])
    body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(body.encode()).hexdigest()


def build_reviewer_policy(declaration: ReviewerPolicyDeclaration) -> ReviewerPolicy:
    """Normalize a reviewer declaration into a self-fingerprinted policy."""
    return ReviewerPolicy(
        schema_version=declaration.schema_version,
        benchmark_id=declaration.benchmark_id,
        operator_id=declaration.operator_id,
        reviewer_ids=tuple(sorted(declaration.reviewer_ids)),
        minimum_distinct_reviewers=declaration.minimum_distinct_reviewers,
        policy_sha256=_policy_sha256(declaration),
    )


def validate_reviewer_separation(
    policy: ReviewerPolicy,
    reviews: AdjudicationReviews,
) -> None:
    """Validate declared structural separation; this is not identity authentication."""
    if reviews.benchmark_id != policy.benchmark_id:
        raise ValueError("review policy benchmark_id does not match reviews")
    if reviews.review_policy_sha256 != policy.policy_sha256:
        raise ValueError("review policy fingerprint does not match reviews")
    reviewer_ids = [decision.reviewer_id for decision in reviews.decisions]
    if policy.operator_id in reviewer_ids:
        raise ValueError("operator must not review campaign decisions")
    unauthorized = sorted(set(reviewer_ids) - set(policy.reviewer_ids))
    if unauthorized:
        raise ValueError(f"reviewer id is not allowed: {', '.join(unauthorized)}")
    if len(set(reviewer_ids)) < policy.minimum_distinct_reviewers:
        raise ValueError("distinct reviewer count is below policy minimum")


def validate_reviewer_policy_capacity(
    policy: ReviewerPolicy,
    *,
    decision_count: int,
) -> None:
    """Reject policies that cannot be satisfied by the campaign decision matrix."""
    if policy.minimum_distinct_reviewers > decision_count:
        raise ValueError("minimum distinct reviewers exceeds campaign decision count")

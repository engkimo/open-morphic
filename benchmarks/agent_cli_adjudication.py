"""Deterministically join recorder evidence and independent review decisions."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.agent_cli_comparison import (
    SCHEMA_VERSION,
    AgentCliArm,
    AgentCliManifest,
    RecordedResults,
    TrialObservation,
)
from benchmarks.agent_cli_receipts import ProviderReceipt

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid", frozen=True)


class HashedCommandEvidence(_FrozenModel):
    argv_sha256: str = Field(pattern=_SHA256_PATTERN)
    exit_code: int
    timed_out: bool
    elapsed_seconds: float = Field(ge=0.0)
    stdout_sha256: str = Field(pattern=_SHA256_PATTERN)
    stdout_bytes: int = Field(ge=0)
    stderr_sha256: str = Field(pattern=_SHA256_PATTERN)
    stderr_bytes: int = Field(ge=0)

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class RecordedTrialEvidence(_FrozenModel):
    arm: AgentCliArm
    trial: int = Field(ge=1)
    reserved_cost_usd: float = Field(ge=0.0)
    agent: HashedCommandEvidence
    checks: dict[str, HashedCommandEvidence]
    handoff_assertions: dict[str, HashedCommandEvidence]
    receipt: ProviderReceipt | None
    completed: bool
    passed_checks: tuple[str, ...]
    passed_handoff_assertions: tuple[str, ...]

    @model_validator(mode="after")
    def validate_derived_fields(self) -> RecordedTrialEvidence:
        if self.completed != self.agent.passed:
            raise ValueError("completed does not match agent command evidence")
        if len(self.passed_checks) != len(set(self.passed_checks)):
            raise ValueError("passed_checks must be unique")
        calculated_checks = {name for name, evidence in self.checks.items() if evidence.passed}
        if set(self.passed_checks) != calculated_checks:
            raise ValueError("passed_checks do not match command evidence")
        if len(self.passed_handoff_assertions) != len(set(self.passed_handoff_assertions)):
            raise ValueError("passed_handoff_assertions must be unique")
        calculated_handoffs = {
            name for name, evidence in self.handoff_assertions.items() if evidence.passed
        }
        if set(self.passed_handoff_assertions) != calculated_handoffs:
            raise ValueError("passed_handoff_assertions do not match command evidence")
        return self


class RecordedEvidence(_FrozenModel):
    schema_version: int
    benchmark_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    workspace_revision: str = Field(min_length=1)
    estimated_max_cost_usd: float = Field(ge=0.0)
    authorized_cost_cap_usd: float = Field(ge=0.0)
    cost_collection: Literal["pending_adjudication", "normalized_receipts"]
    trials: tuple[RecordedTrialEvidence, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_schema(self) -> RecordedEvidence:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        return self


class ReviewDecision(_FrozenModel):
    arm: AgentCliArm
    trial: int = Field(ge=1)
    agent_argv_sha256: str = Field(pattern=_SHA256_PATTERN)
    accepted_patch: bool
    human_interventions: int = Field(ge=0)
    recovery_attempted: bool
    recovery_succeeded: bool
    reviewer_id: str = Field(min_length=1)
    review_artifact_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_recovery(self) -> ReviewDecision:
        if self.recovery_succeeded and not self.recovery_attempted:
            raise ValueError("recovery_succeeded requires recovery_attempted=true")
        return self


class AdjudicationReviews(_FrozenModel):
    schema_version: int
    benchmark_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    workspace_revision: str = Field(min_length=1)
    preflight_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    evidence_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    review_policy_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    review_completed: Literal[True] | None = None
    decisions: tuple[ReviewDecision, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_schema(self) -> AdjudicationReviews:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        return self


def recorded_evidence_sha256(evidence: RecordedEvidence) -> str:
    """Fingerprint the complete normalized evidence artifact deterministically."""
    payload = json.dumps(
        evidence.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _validate_identity(
    manifest: AgentCliManifest,
    evidence: RecordedEvidence,
    reviews: AdjudicationReviews,
) -> None:
    expected = (manifest.benchmark_id, manifest.task.id, manifest.task.workspace_revision)
    if (evidence.benchmark_id, evidence.task_id, evidence.workspace_revision) != expected:
        raise ValueError("evidence identity does not match manifest")
    if (reviews.benchmark_id, reviews.task_id, reviews.workspace_revision) != expected:
        raise ValueError("review identity does not match manifest")


def _index_complete_matrix(
    rows: tuple[RecordedTrialEvidence, ...] | tuple[ReviewDecision, ...],
    expected: set[tuple[AgentCliArm, int]],
    *,
    label: str,
) -> dict[tuple[AgentCliArm, int], RecordedTrialEvidence | ReviewDecision]:
    indexed: dict[tuple[AgentCliArm, int], RecordedTrialEvidence | ReviewDecision] = {}
    for row in rows:
        key = (row.arm, row.trial)
        if key in indexed:
            raise ValueError(f"duplicate {label}: {row.arm.value}:{row.trial}")
        indexed[key] = row
    missing = expected - set(indexed)
    extra = set(indexed) - expected
    if missing:
        details = ", ".join(f"{arm.value}:{trial}" for arm, trial in sorted(missing))
        raise ValueError(f"missing {label}: {details}")
    if extra:
        details = ", ".join(f"{arm.value}:{trial}" for arm, trial in sorted(extra))
        raise ValueError(f"unexpected {label}: {details}")
    return indexed


def finalize_recorded_results(
    manifest: AgentCliManifest,
    evidence: RecordedEvidence,
    reviews: AdjudicationReviews,
) -> RecordedResults:
    """Create Phase 40 observations only after every evidence join validates."""
    _validate_identity(manifest, evidence, reviews)
    if (
        reviews.evidence_sha256 is not None
        and reviews.evidence_sha256 != recorded_evidence_sha256(evidence)
    ):
        raise ValueError("review evidence fingerprint does not match evidence")
    if evidence.cost_collection != "normalized_receipts":
        raise ValueError("evidence cost_collection is not normalized_receipts")
    expected = {
        (arm, trial)
        for arm in manifest.arms
        for trial in range(1, manifest.repetitions + 1)
    }
    evidence_by_key = _index_complete_matrix(evidence.trials, expected, label="evidence")
    reviews_by_key = _index_complete_matrix(reviews.decisions, expected, label="review")

    observations: list[TrialObservation] = []
    total_cost = 0.0
    for arm in manifest.arms:
        for trial_number in range(1, manifest.repetitions + 1):
            key = (arm, trial_number)
            trial = evidence_by_key[key]
            review = reviews_by_key[key]
            assert isinstance(trial, RecordedTrialEvidence)
            assert isinstance(review, ReviewDecision)
            if set(trial.checks) != set(manifest.task.checks):
                raise ValueError(f"check evidence mismatch for {arm.value}:{trial_number}")
            if set(trial.handoff_assertions) != set(manifest.task.handoff_assertions):
                raise ValueError(f"handoff evidence mismatch for {arm.value}:{trial_number}")
            if trial.receipt is None:
                raise ValueError(f"receipt missing for {arm.value}:{trial_number}")
            if trial.receipt.provider is not arm:
                raise ValueError(f"receipt provider mismatch for {arm.value}:{trial_number}")
            if trial.receipt.parse_errors:
                raise ValueError(f"receipt contains parse errors for {arm.value}:{trial_number}")
            if review.agent_argv_sha256 != trial.agent.argv_sha256:
                raise ValueError(f"review fingerprint mismatch for {arm.value}:{trial_number}")

            completed = trial.completed and trial.receipt.success
            if review.accepted_patch and not completed:
                raise ValueError(
                    f"accepted_patch requires completed trial for {arm.value}:{trial_number}"
                )
            if review.recovery_succeeded and not completed:
                raise ValueError(
                    f"recovery_succeeded requires completed trial for {arm.value}:{trial_number}"
                )
            total_cost += trial.receipt.cost_usd
            observations.append(
                TrialObservation(
                    arm=arm,
                    trial=trial_number,
                    completed=completed,
                    accepted_patch=review.accepted_patch,
                    passed_checks=tuple(
                        name for name in manifest.task.checks if trial.checks[name].passed
                    ),
                    elapsed_seconds=trial.agent.elapsed_seconds,
                    cost_usd=trial.receipt.cost_usd,
                    human_interventions=review.human_interventions,
                    recovery_attempted=review.recovery_attempted,
                    recovery_succeeded=review.recovery_succeeded,
                    passed_handoff_assertions=tuple(
                        name
                        for name in manifest.task.handoff_assertions
                        if trial.handoff_assertions[name].passed
                    ),
                )
            )

    if round(total_cost, 6) > evidence.authorized_cost_cap_usd:
        raise ValueError(
            "normalized receipt total exceeds authorized cost cap "
            f"(${total_cost:.6f} > ${evidence.authorized_cost_cap_usd:.6f})"
        )
    return RecordedResults(
        schema_version=SCHEMA_VERSION,
        benchmark_id=manifest.benchmark_id,
        task_id=manifest.task.id,
        observations=tuple(observations),
    )


def finalized_results_json(results: RecordedResults) -> str:
    return json.dumps(results.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)

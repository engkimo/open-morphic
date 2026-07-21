"""Offline campaign preflight and evidence-bound review template generation."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.agent_cli_adjudication import (
    AdjudicationReviews,
    RecordedEvidence,
    RecordedTrialEvidence,
    recorded_evidence_sha256,
)
from benchmarks.agent_cli_comparison import (
    REQUIRED_ARMS,
    SCHEMA_VERSION,
    AgentCliArm,
    AgentCliManifest,
)
from benchmarks.agent_cli_recorder import (
    AgentCliRecorderConfig,
    build_recording_plan,
)
from benchmarks.agent_cli_rehearsal import resolve_git_revision as _resolve_git_revision

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


async def resolve_git_revision(source_root: Path, revision: str) -> str:
    """Resolve the campaign revision through the shared read-only Git helper."""
    return await _resolve_git_revision(source_root, revision)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid", frozen=True)


class RuntimeVersionDeclaration(_FrozenModel):
    executable: str = Field(min_length=1, max_length=1024)
    version: str = Field(min_length=1, max_length=500)


class RuntimeVersionBundle(_FrozenModel):
    schema_version: int
    benchmark_id: str = Field(min_length=1)
    runtimes: dict[AgentCliArm, RuntimeVersionDeclaration]

    @model_validator(mode="after")
    def validate_contract(self) -> RuntimeVersionBundle:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if set(self.runtimes) != REQUIRED_ARMS:
            raise ValueError("runtimes must contain exactly the three comparison arms")
        return self


class RuntimeFingerprint(_FrozenModel):
    executable: str = Field(min_length=1, max_length=1024)
    version: str = Field(min_length=1, max_length=500)
    version_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_fingerprint(self) -> RuntimeFingerprint:
        if self.version != _normalize_version(self.version):
            raise ValueError("runtime version must be whitespace-normalized")
        expected = hashlib.sha256(self.version.encode()).hexdigest()
        if self.version_sha256 != expected:
            raise ValueError("runtime version fingerprint does not match version")
        return self


def _normalize_version(version: str) -> str:
    normalized = " ".join(version.split())
    if not normalized:
        raise ValueError("runtime version must not be blank")
    return normalized


def _canonical_sha256(payload: object) -> str:
    body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(body.encode()).hexdigest()


class CampaignPreflight(_FrozenModel):
    schema_version: int
    benchmark_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    arms: tuple[AgentCliArm, ...]
    repetitions: int = Field(ge=1)
    trial_count: int = Field(ge=1)
    estimated_max_cost_usd: float = Field(ge=0.0)
    manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    config_sha256: str = Field(pattern=_SHA256_PATTERN)
    command_fingerprints: dict[str, str]
    runtime_fingerprints: dict[AgentCliArm, RuntimeFingerprint]
    execution_authorized: Literal[False] = False
    preflight_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> CampaignPreflight:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if len(self.arms) != len(REQUIRED_ARMS) or set(self.arms) != REQUIRED_ARMS:
            raise ValueError("preflight arms must contain exactly the comparison arms")
        if set(self.runtime_fingerprints) != REQUIRED_ARMS:
            raise ValueError("runtime fingerprints must contain exactly the comparison arms")
        if self.trial_count != len(self.arms) * self.repetitions:
            raise ValueError("trial_count does not match arms and repetitions")
        if not self.command_fingerprints or any(
            re.fullmatch(_SHA256_PATTERN, fingerprint) is None
            for fingerprint in self.command_fingerprints.values()
        ):
            raise ValueError("command fingerprints must be non-empty SHA-256 values")
        expected = _canonical_sha256(self._binding_payload())
        if self.preflight_sha256 != expected:
            raise ValueError("preflight fingerprint does not match report")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"preflight_sha256"})

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def build_campaign_preflight(
    manifest: AgentCliManifest,
    config: AgentCliRecorderConfig,
    versions: RuntimeVersionBundle,
    *,
    resolved_revision: str,
) -> CampaignPreflight:
    """Validate a fully pinned campaign without authorizing or launching agents."""
    if not _COMMIT_PATTERN.fullmatch(resolved_revision):
        raise ValueError("resolved revision must be a full lowercase Git commit")
    if manifest.task.workspace_revision != resolved_revision:
        raise ValueError("manifest must pin the immutable resolved revision")
    if versions.benchmark_id != manifest.benchmark_id:
        raise ValueError("runtime versions benchmark_id does not match manifest")
    plan = build_recording_plan(manifest, config)
    runtime_fingerprints: dict[AgentCliArm, RuntimeFingerprint] = {}
    for arm in manifest.arms:
        declaration = versions.runtimes[arm]
        expected_executable = config.arm_commands[arm][0]
        if declaration.executable != expected_executable:
            raise ValueError(f"runtime executable does not match {arm.value} command")
        normalized_version = _normalize_version(declaration.version)
        runtime_fingerprints[arm] = RuntimeFingerprint(
            executable=declaration.executable,
            version=normalized_version,
            version_sha256=hashlib.sha256(normalized_version.encode()).hexdigest(),
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "benchmark_id": manifest.benchmark_id,
        "task_id": manifest.task.id,
        "workspace_revision": resolved_revision,
        "arms": [arm.value for arm in manifest.arms],
        "repetitions": manifest.repetitions,
        "trial_count": plan.trial_count,
        "estimated_max_cost_usd": plan.estimated_max_cost_usd,
        "manifest_sha256": _canonical_sha256(manifest.model_dump(mode="json")),
        "config_sha256": _canonical_sha256(config.model_dump(mode="json")),
        "command_fingerprints": plan.command_fingerprints,
        "runtime_fingerprints": {
            arm.value: fingerprint.model_dump(mode="json")
            for arm, fingerprint in runtime_fingerprints.items()
        },
        "execution_authorized": False,
    }
    return CampaignPreflight(
        **payload,
        preflight_sha256=_canonical_sha256(payload),
    )


class ReviewDecisionTemplate(_FrozenModel):
    arm: AgentCliArm
    trial: int = Field(ge=1)
    agent_argv_sha256: str = Field(pattern=_SHA256_PATTERN)
    accepted_patch: None = None
    human_interventions: None = None
    recovery_attempted: None = None
    recovery_succeeded: None = None
    reviewer_id: None = None
    review_artifact_sha256: None = None


class ReviewTemplate(_FrozenModel):
    schema_version: int
    benchmark_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    preflight_sha256: str = Field(pattern=_SHA256_PATTERN)
    evidence_sha256: str = Field(pattern=_SHA256_PATTERN)
    decisions: tuple[ReviewDecisionTemplate, ...] = Field(min_length=1)
    review_completed: Literal[False] = False

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _expected_cells(preflight: CampaignPreflight) -> set[tuple[AgentCliArm, int]]:
    return {
        (arm, trial)
        for arm in preflight.arms
        for trial in range(1, preflight.repetitions + 1)
    }


def build_review_template(
    preflight: CampaignPreflight,
    evidence: RecordedEvidence,
) -> ReviewTemplate:
    """Create null review decisions bound to exact preflight and evidence artifacts."""
    expected_identity = (
        preflight.benchmark_id,
        preflight.task_id,
        preflight.workspace_revision,
    )
    if (
        evidence.benchmark_id,
        evidence.task_id,
        evidence.workspace_revision,
    ) != expected_identity:
        raise ValueError("evidence identity does not match preflight")
    indexed: dict[tuple[AgentCliArm, int], RecordedTrialEvidence] = {}
    for trial in evidence.trials:
        key = (trial.arm, trial.trial)
        if key in indexed:
            raise ValueError(f"duplicate evidence for {trial.arm.value}:{trial.trial}")
        indexed[key] = trial
    expected = _expected_cells(preflight)
    if set(indexed) != expected:
        raise ValueError("evidence trial matrix does not match preflight")
    decisions = tuple(
        ReviewDecisionTemplate(
            arm=arm,
            trial=trial_number,
            agent_argv_sha256=indexed[(arm, trial_number)].agent.argv_sha256,
        )
        for arm in preflight.arms
        for trial_number in range(1, preflight.repetitions + 1)
    )
    return ReviewTemplate(
        schema_version=SCHEMA_VERSION,
        benchmark_id=preflight.benchmark_id,
        task_id=preflight.task_id,
        workspace_revision=preflight.workspace_revision,
        preflight_sha256=preflight.preflight_sha256,
        evidence_sha256=recorded_evidence_sha256(evidence),
        decisions=decisions,
    )


def validate_review_bindings(
    preflight: CampaignPreflight,
    evidence: RecordedEvidence,
    reviews: AdjudicationReviews,
) -> None:
    """Require completed reviews to retain their generated artifact bindings."""
    if reviews.preflight_sha256 != preflight.preflight_sha256:
        raise ValueError("review preflight fingerprint does not match preflight")
    if reviews.evidence_sha256 != recorded_evidence_sha256(evidence):
        raise ValueError("review evidence fingerprint does not match evidence")
    expected_identity = (
        preflight.benchmark_id,
        preflight.task_id,
        preflight.workspace_revision,
    )
    if (
        reviews.benchmark_id,
        reviews.task_id,
        reviews.workspace_revision,
    ) != expected_identity:
        raise ValueError("review identity does not match preflight")

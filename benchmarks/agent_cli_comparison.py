"""Deterministic evaluation for recorded same-task agent CLI trials.

This module never launches an agent engine. It validates observations captured
against one manifest and compares the three supported arms without inventing a
weighted composite score.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from statistics import median
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1


class AgentCliArm(str, Enum):
    """A supported arm in the same-task comparison."""

    CODEX_CLI = "codex_cli"
    CLAUDE_CODE = "claude_code"
    MORPHIC_CONTROL = "morphic_control"


REQUIRED_ARMS = frozenset(AgentCliArm)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid", frozen=True)


class BenchmarkTask(_FrozenModel):
    """One immutable task definition shared by every trial."""

    id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    workspace_revision: str = Field(min_length=1)
    checks: tuple[str, ...] = Field(min_length=1)
    handoff_assertions: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_checks(self) -> BenchmarkTask:
        if any(not check.strip() for check in self.checks):
            raise ValueError("task checks must not be blank")
        if len(set(self.checks)) != len(self.checks):
            raise ValueError("task checks must be unique")
        if any(not assertion.strip() for assertion in self.handoff_assertions):
            raise ValueError("task handoff_assertions must not be blank")
        if len(set(self.handoff_assertions)) != len(self.handoff_assertions):
            raise ValueError("task handoff_assertions must be unique")
        return self


class AgentCliManifest(_FrozenModel):
    """Reproducible contract for a same-task comparison."""

    schema_version: int
    benchmark_id: str = Field(min_length=1)
    task: BenchmarkTask
    arms: tuple[AgentCliArm, ...]
    repetitions: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_contract(self) -> AgentCliManifest:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if len(self.arms) != len(REQUIRED_ARMS) or set(self.arms) != REQUIRED_ARMS:
            expected = ", ".join(arm.value for arm in AgentCliArm)
            raise ValueError(f"arms must contain exactly: {expected}")
        return self


class TrialObservation(_FrozenModel):
    """One recorded trial; all metrics are supplied by the recorder."""

    arm: AgentCliArm
    trial: int = Field(ge=1)
    completed: bool
    accepted_patch: bool
    passed_checks: tuple[str, ...]
    elapsed_seconds: float = Field(ge=0.0)
    cost_usd: float = Field(ge=0.0)
    human_interventions: int = Field(ge=0)
    recovery_attempted: bool
    recovery_succeeded: bool
    passed_handoff_assertions: tuple[str, ...]

    @model_validator(mode="after")
    def validate_outcomes(self) -> TrialObservation:
        if self.accepted_patch and not self.completed:
            raise ValueError("accepted_patch requires completed=true")
        if self.recovery_succeeded and not self.recovery_attempted:
            raise ValueError("recovery_succeeded requires recovery_attempted=true")
        if len(set(self.passed_checks)) != len(self.passed_checks):
            raise ValueError("passed_checks must be unique")
        if len(set(self.passed_handoff_assertions)) != len(self.passed_handoff_assertions):
            raise ValueError("passed_handoff_assertions must be unique")
        return self


class RecordedResults(_FrozenModel):
    """Recorded observations for one manifest."""

    schema_version: int
    benchmark_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    observations: tuple[TrialObservation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_schema_version(self) -> RecordedResults:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        return self


@dataclass(frozen=True)
class ArmMetrics:
    """Unweighted metrics for one comparison arm."""

    accepted_patch_rate: float
    completion_rate: float
    context_handoff_score: float
    mean_cost_usd: float
    mean_human_interventions: float
    median_elapsed_seconds: float
    recovery_rate: float | None
    verification_rate: float


@dataclass(frozen=True)
class AgentCliReport:
    """Deterministic same-task comparison report."""

    schema_version: int
    benchmark_id: str
    task_id: str
    workspace_revision: str
    observation_count: int
    arms: dict[str, ArmMetrics]
    leaders: dict[str, list[str]]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe report without timestamps or environment state."""
        return {
            "schema_version": self.schema_version,
            "benchmark_id": self.benchmark_id,
            "task_id": self.task_id,
            "workspace_revision": self.workspace_revision,
            "observation_count": self.observation_count,
            "arms": {name: asdict(metrics) for name, metrics in self.arms.items()},
            "leaders": self.leaders,
        }

    def to_json(self) -> str:
        """Serialize deterministically for diffs and CI artifacts."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


def _round(value: float) -> float:
    return round(value, 6)


def _calculate_metrics(
    observations: list[TrialObservation],
    check_count: int,
    handoff_assertion_count: int,
) -> ArmMetrics:
    count = len(observations)
    recovery_trials = [row for row in observations if row.recovery_attempted]
    recovery_rate = (
        _round(sum(row.recovery_succeeded for row in recovery_trials) / len(recovery_trials))
        if recovery_trials
        else None
    )
    return ArmMetrics(
        accepted_patch_rate=_round(sum(row.accepted_patch for row in observations) / count),
        completion_rate=_round(sum(row.completed for row in observations) / count),
        context_handoff_score=_round(
            sum(len(row.passed_handoff_assertions) for row in observations)
            / (count * handoff_assertion_count)
        ),
        mean_cost_usd=_round(sum(row.cost_usd for row in observations) / count),
        mean_human_interventions=_round(
            sum(row.human_interventions for row in observations) / count
        ),
        median_elapsed_seconds=_round(median(row.elapsed_seconds for row in observations)),
        recovery_rate=recovery_rate,
        verification_rate=_round(
            sum(len(row.passed_checks) for row in observations) / (count * check_count)
        ),
    )


def _metric_leaders(
    arms: dict[str, ArmMetrics],
    metric: str,
    *,
    lower_is_better: bool,
) -> list[str]:
    values = {
        arm: value
        for arm, metrics in arms.items()
        if (value := getattr(metrics, metric)) is not None
    }
    if not values:
        return []
    best = min(values.values()) if lower_is_better else max(values.values())
    return sorted(arm for arm, value in values.items() if value == best)


def evaluate_recorded_results(
    manifest: AgentCliManifest,
    results: RecordedResults,
) -> AgentCliReport:
    """Validate and compare a complete recorded result set."""
    if results.benchmark_id != manifest.benchmark_id:
        raise ValueError("results benchmark_id does not match manifest")
    if results.task_id != manifest.task.id:
        raise ValueError("results task_id does not match manifest")

    declared_checks = set(manifest.task.checks)
    declared_handoff_assertions = set(manifest.task.handoff_assertions)
    seen: set[tuple[AgentCliArm, int]] = set()
    for observation in results.observations:
        key = (observation.arm, observation.trial)
        if key in seen:
            raise ValueError(
                f"duplicate observation for {observation.arm.value} trial {observation.trial}"
            )
        seen.add(key)
        unknown_checks = set(observation.passed_checks) - declared_checks
        if unknown_checks:
            names = ", ".join(sorted(unknown_checks))
            raise ValueError(f"observation contains undeclared checks: {names}")
        unknown_assertions = (
            set(observation.passed_handoff_assertions) - declared_handoff_assertions
        )
        if unknown_assertions:
            names = ", ".join(sorted(unknown_assertions))
            raise ValueError(f"observation contains undeclared handoff assertions: {names}")

    expected = {
        (arm, trial)
        for arm in manifest.arms
        for trial in range(1, manifest.repetitions + 1)
    }
    missing = expected - seen
    extra = seen - expected
    if missing:
        details = ", ".join(f"{arm.value}:{trial}" for arm, trial in sorted(missing))
        raise ValueError(f"missing observations: {details}")
    if extra:
        details = ", ".join(f"{arm.value}:{trial}" for arm, trial in sorted(extra))
        raise ValueError(f"unexpected observations: {details}")

    arm_metrics = {
        arm.value: _calculate_metrics(
            [row for row in results.observations if row.arm == arm],
            len(manifest.task.checks),
            len(manifest.task.handoff_assertions),
        )
        for arm in manifest.arms
    }
    lower_is_better = {
        "accepted_patch_rate": False,
        "completion_rate": False,
        "context_handoff_score": False,
        "mean_cost_usd": True,
        "mean_human_interventions": True,
        "median_elapsed_seconds": True,
        "recovery_rate": False,
        "verification_rate": False,
    }
    leaders = {
        metric: _metric_leaders(arm_metrics, metric, lower_is_better=lower)
        for metric, lower in lower_is_better.items()
    }
    return AgentCliReport(
        schema_version=SCHEMA_VERSION,
        benchmark_id=manifest.benchmark_id,
        task_id=manifest.task.id,
        workspace_revision=manifest.task.workspace_revision,
        observation_count=len(results.observations),
        arms=arm_metrics,
        leaders=leaders,
    )

"""Explicit opt-in recorder for isolated same-task agent CLI trials.

Dry-run planning is pure and deterministic. Live execution requires a separate
paid-run acknowledgement and an explicit cost cap. Each trial runs in a detached
Git worktree, and evidence stores hashes and byte counts instead of raw output.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.agent_cli_comparison import (
    REQUIRED_ARMS,
    SCHEMA_VERSION,
    AgentCliArm,
    AgentCliManifest,
)
from benchmarks.agent_cli_receipts import ProviderReceipt, ProviderReceiptParser


class _FrozenModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid", frozen=True)


def _validate_command_map(name: str, commands: dict[Any, tuple[str, ...]]) -> None:
    for key, argv in commands.items():
        if not argv:
            raise ValueError(f"{name}[{key}] must not be empty")
        if any(not argument or "\x00" in argument for argument in argv):
            raise ValueError(f"{name}[{key}] arguments must be non-empty and NUL-free")


class AgentCliRecorderConfig(_FrozenModel):
    """Commands and safety estimates for one recorded benchmark."""

    schema_version: int
    benchmark_id: str = Field(min_length=1)
    arm_commands: dict[AgentCliArm, tuple[str, ...]]
    check_commands: dict[str, tuple[str, ...]]
    handoff_commands: dict[str, tuple[str, ...]]
    estimated_cost_usd_per_trial: dict[AgentCliArm, float]
    model_hints: dict[AgentCliArm, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(gt=0.0, le=3600.0)

    @model_validator(mode="after")
    def validate_config(self) -> AgentCliRecorderConfig:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if set(self.arm_commands) != REQUIRED_ARMS:
            raise ValueError("arm_commands must contain exactly the three comparison arms")
        if set(self.estimated_cost_usd_per_trial) != REQUIRED_ARMS:
            raise ValueError(
                "estimated_cost_usd_per_trial must contain exactly the three comparison arms"
            )
        if any(value < 0.0 for value in self.estimated_cost_usd_per_trial.values()):
            raise ValueError("estimated costs must be non-negative")
        if not set(self.model_hints).issubset(REQUIRED_ARMS):
            raise ValueError("model_hints contains an unsupported arm")
        if any(not model.strip() for model in self.model_hints.values()):
            raise ValueError("model_hints values must not be blank")
        _validate_command_map("arm_commands", self.arm_commands)
        _validate_command_map("check_commands", self.check_commands)
        _validate_command_map("handoff_commands", self.handoff_commands)
        return self


def _argv_sha256(argv: tuple[str, ...]) -> str:
    body = json.dumps(argv, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


@dataclass(frozen=True)
class RecordingPlan:
    """Deterministic preview; it contains no raw task prompt."""

    schema_version: int
    benchmark_id: str
    task_id: str
    workspace_revision: str
    repetitions: int
    arms: list[str]
    trial_count: int
    estimated_max_cost_usd: float
    timeout_seconds: float
    command_fingerprints: dict[str, str]
    execution_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


def build_recording_plan(
    manifest: AgentCliManifest,
    config: AgentCliRecorderConfig,
) -> RecordingPlan:
    """Validate recorder coverage and return a non-executing preview."""
    if config.benchmark_id != manifest.benchmark_id:
        raise ValueError("recorder benchmark_id does not match manifest")
    if set(config.arm_commands) != set(manifest.arms):
        raise ValueError("arm_commands do not match manifest arms")
    if set(config.check_commands) != set(manifest.task.checks):
        raise ValueError("check_commands do not match manifest checks")
    if set(config.handoff_commands) != set(manifest.task.handoff_assertions):
        raise ValueError("handoff_commands do not match manifest handoff_assertions")

    fingerprints = {
        **{
            f"arm:{arm.value}": _argv_sha256(config.arm_commands[arm])
            for arm in manifest.arms
        },
        **{
            f"check:{name}": _argv_sha256(config.check_commands[name])
            for name in sorted(config.check_commands)
        },
        **{
            f"handoff:{name}": _argv_sha256(config.handoff_commands[name])
            for name in sorted(config.handoff_commands)
        },
    }
    estimated_cost = sum(
        config.estimated_cost_usd_per_trial[arm] * manifest.repetitions
        for arm in manifest.arms
    )
    return RecordingPlan(
        schema_version=SCHEMA_VERSION,
        benchmark_id=manifest.benchmark_id,
        task_id=manifest.task.id,
        workspace_revision=manifest.task.workspace_revision,
        repetitions=manifest.repetitions,
        arms=[arm.value for arm in manifest.arms],
        trial_count=len(manifest.arms) * manifest.repetitions,
        estimated_max_cost_usd=round(estimated_cost, 6),
        timeout_seconds=config.timeout_seconds,
        command_fingerprints=fingerprints,
    )


def validate_execution_consent(
    plan: RecordingPlan,
    *,
    acknowledged_paid: bool,
    cost_cap_usd: float | None,
) -> None:
    """Fail before filesystem mutation unless live-run consent is complete."""
    if not acknowledged_paid:
        raise ValueError("paid execution acknowledgement is required")
    if cost_cap_usd is None or not math.isfinite(cost_cap_usd) or cost_cap_usd < 0.0:
        raise ValueError("a finite non-negative cost cap is required")
    if cost_cap_usd < plan.estimated_max_cost_usd:
        raise ValueError(
            "cost cap is below estimated maximum "
            f"(${cost_cap_usd:.6f} < ${plan.estimated_max_cost_usd:.6f})"
        )


@dataclass(frozen=True)
class CommandCapture:
    """Ephemeral raw command result returned by a runner."""

    exit_code: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    timed_out: bool


@dataclass(frozen=True)
class CommandEvidence:
    """Persistable command evidence with raw output removed."""

    argv_sha256: str
    exit_code: int
    timed_out: bool
    elapsed_seconds: float
    stdout_sha256: str
    stdout_bytes: int
    stderr_sha256: str
    stderr_bytes: int

    @classmethod
    def from_capture(
        cls,
        *,
        argv: tuple[str, ...],
        capture: CommandCapture,
    ) -> CommandEvidence:
        stdout = capture.stdout.encode()
        stderr = capture.stderr.encode()
        return cls(
            argv_sha256=_argv_sha256(argv),
            exit_code=capture.exit_code,
            timed_out=capture.timed_out,
            elapsed_seconds=round(capture.elapsed_seconds, 6),
            stdout_sha256=hashlib.sha256(stdout).hexdigest(),
            stdout_bytes=len(stdout),
            stderr_sha256=hashlib.sha256(stderr).hexdigest(),
            stderr_bytes=len(stderr),
        )


@dataclass(frozen=True)
class TrialEvidence:
    arm: str
    trial: int
    reserved_cost_usd: float
    agent: CommandEvidence
    checks: dict[str, CommandEvidence]
    handoff_assertions: dict[str, CommandEvidence]
    receipt: ProviderReceipt | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "trial": self.trial,
            "reserved_cost_usd": self.reserved_cost_usd,
            "agent": asdict(self.agent),
            "checks": {name: asdict(value) for name, value in self.checks.items()},
            "handoff_assertions": {
                name: asdict(value) for name, value in self.handoff_assertions.items()
            },
            "receipt": (
                self.receipt.model_dump(mode="json") if self.receipt is not None else None
            ),
            "completed": self.agent.exit_code == 0 and not self.agent.timed_out,
            "passed_checks": [
                name
                for name, value in self.checks.items()
                if value.exit_code == 0 and not value.timed_out
            ],
            "passed_handoff_assertions": [
                name
                for name, value in self.handoff_assertions.items()
                if value.exit_code == 0 and not value.timed_out
            ],
        }


@dataclass(frozen=True)
class RecordingEvidence:
    schema_version: int
    benchmark_id: str
    task_id: str
    workspace_revision: str
    estimated_max_cost_usd: float
    authorized_cost_cap_usd: float
    trials: list[TrialEvidence]

    def to_dict(self) -> dict[str, Any]:
        cost_collection = (
            "normalized_receipts"
            if all(trial.receipt is not None for trial in self.trials)
            else "pending_adjudication"
        )
        return {
            "schema_version": self.schema_version,
            "benchmark_id": self.benchmark_id,
            "task_id": self.task_id,
            "workspace_revision": self.workspace_revision,
            "estimated_max_cost_usd": self.estimated_max_cost_usd,
            "authorized_cost_cap_usd": self.authorized_cost_cap_usd,
            "cost_collection": cost_collection,
            "trials": [trial.to_dict() for trial in self.trials],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


class WorktreeManagerPort(Protocol):
    async def create(self, *, source_root: Path, revision: str, destination: Path) -> None: ...

    async def release(self, *, source_root: Path, destination: Path) -> None: ...


class CommandRunnerPort(Protocol):
    async def run(
        self,
        *,
        argv: tuple[str, ...],
        cwd: Path,
        timeout_seconds: float,
    ) -> CommandCapture: ...


class ReceiptParserPort(Protocol):
    def parse(
        self,
        *,
        arm: AgentCliArm | str,
        stdout: str,
        model_hint: str | None = None,
    ) -> ProviderReceipt | None: ...


def _expand_argv(
    template: tuple[str, ...],
    *,
    manifest: AgentCliManifest,
    arm: AgentCliArm,
    trial: int,
    workspace: Path,
) -> tuple[str, ...]:
    replacements = {
        "{goal}": manifest.task.goal,
        "{workspace}": str(workspace),
        "{arm}": arm.value,
        "{trial}": str(trial),
    }
    return tuple(
        argument.replace("{goal}", replacements["{goal}"])
        .replace("{workspace}", replacements["{workspace}"])
        .replace("{arm}", replacements["{arm}"])
        .replace("{trial}", replacements["{trial}"])
        for argument in template
    )


class AgentCliTrialRecorder:
    """Run a complete trial matrix through injected isolation and command ports."""

    def __init__(
        self,
        *,
        worktree_manager: WorktreeManagerPort,
        command_runner: CommandRunnerPort,
        receipt_parser: ReceiptParserPort | None = None,
    ) -> None:
        self._worktree_manager = worktree_manager
        self._command_runner = command_runner
        self._receipt_parser = receipt_parser or ProviderReceiptParser()

    async def record(
        self,
        *,
        manifest: AgentCliManifest,
        config: AgentCliRecorderConfig,
        source_root: Path,
        worktree_root: Path,
        acknowledged_paid: bool,
        cost_cap_usd: float | None,
    ) -> RecordingEvidence:
        plan = build_recording_plan(manifest, config)
        validate_execution_consent(
            plan,
            acknowledged_paid=acknowledged_paid,
            cost_cap_usd=cost_cap_usd,
        )
        assert cost_cap_usd is not None
        source_root = source_root.resolve()
        worktree_root = worktree_root.resolve()
        if worktree_root == source_root or worktree_root.is_relative_to(source_root):
            raise ValueError("worktree_root must be outside source_root")
        worktree_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        trials: list[TrialEvidence] = []
        prefix = hashlib.sha256(manifest.benchmark_id.encode()).hexdigest()[:12]

        for arm in manifest.arms:
            for trial in range(1, manifest.repetitions + 1):
                destination = worktree_root / f"{prefix}-{arm.value}-{trial}"
                if destination.exists():
                    raise ValueError(f"worktree destination already exists: {destination}")
                created = False
                try:
                    await self._worktree_manager.create(
                        source_root=source_root,
                        revision=manifest.task.workspace_revision,
                        destination=destination,
                    )
                    created = True
                    agent, receipt = await self._run_agent_evidence(
                        config.arm_commands[arm],
                        manifest=manifest,
                        arm=arm,
                        trial=trial,
                        workspace=destination,
                        timeout_seconds=config.timeout_seconds,
                        model_hint=config.model_hints.get(arm),
                    )
                    checks = {
                        name: await self._run_evidence(
                            config.check_commands[name],
                            manifest=manifest,
                            arm=arm,
                            trial=trial,
                            workspace=destination,
                            timeout_seconds=config.timeout_seconds,
                        )
                        for name in manifest.task.checks
                    }
                    handoffs = {
                        name: await self._run_evidence(
                            config.handoff_commands[name],
                            manifest=manifest,
                            arm=arm,
                            trial=trial,
                            workspace=destination,
                            timeout_seconds=config.timeout_seconds,
                        )
                        for name in manifest.task.handoff_assertions
                    }
                    trials.append(
                        TrialEvidence(
                            arm=arm.value,
                            trial=trial,
                            reserved_cost_usd=config.estimated_cost_usd_per_trial[arm],
                            agent=agent,
                            checks=checks,
                            handoff_assertions=handoffs,
                            receipt=receipt,
                        )
                    )
                finally:
                    if created:
                        await self._worktree_manager.release(
                            source_root=source_root,
                            destination=destination,
                        )

        return RecordingEvidence(
            schema_version=SCHEMA_VERSION,
            benchmark_id=manifest.benchmark_id,
            task_id=manifest.task.id,
            workspace_revision=manifest.task.workspace_revision,
            estimated_max_cost_usd=plan.estimated_max_cost_usd,
            authorized_cost_cap_usd=cost_cap_usd,
            trials=trials,
        )

    async def _run_evidence(
        self,
        template: tuple[str, ...],
        *,
        manifest: AgentCliManifest,
        arm: AgentCliArm,
        trial: int,
        workspace: Path,
        timeout_seconds: float,
    ) -> CommandEvidence:
        argv = _expand_argv(
            template,
            manifest=manifest,
            arm=arm,
            trial=trial,
            workspace=workspace,
        )
        capture = await self._command_runner.run(
            argv=argv,
            cwd=workspace,
            timeout_seconds=timeout_seconds,
        )
        return CommandEvidence.from_capture(argv=argv, capture=capture)

    async def _run_agent_evidence(
        self,
        template: tuple[str, ...],
        *,
        manifest: AgentCliManifest,
        arm: AgentCliArm,
        trial: int,
        workspace: Path,
        timeout_seconds: float,
        model_hint: str | None,
    ) -> tuple[CommandEvidence, ProviderReceipt | None]:
        argv = _expand_argv(
            template,
            manifest=manifest,
            arm=arm,
            trial=trial,
            workspace=workspace,
        )
        capture = await self._command_runner.run(
            argv=argv,
            cwd=workspace,
            timeout_seconds=timeout_seconds,
        )
        receipt = self._receipt_parser.parse(
            arm=arm,
            stdout=capture.stdout,
            model_hint=model_hint,
        )
        return CommandEvidence.from_capture(argv=argv, capture=capture), receipt


class LocalCommandRunner:
    """Run one argv vector without invoking a shell."""

    async def run(
        self,
        *,
        argv: tuple[str, ...],
        cwd: Path,
        timeout_seconds: float,
    ) -> CommandCapture:
        started = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            return CommandCapture(
                exit_code=127,
                stdout="",
                stderr=str(exc),
                elapsed_seconds=time.monotonic() - started,
                timed_out=False,
            )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
        except asyncio.CancelledError:
            await _terminate_process(process)
            raise
        except TimeoutError:
            await _terminate_process(process)
            return CommandCapture(
                exit_code=-1,
                stdout="",
                stderr=f"command timed out after {timeout_seconds}s",
                elapsed_seconds=time.monotonic() - started,
                timed_out=True,
            )
        return CommandCapture(
            exit_code=process.returncode or 0,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            elapsed_seconds=time.monotonic() - started,
            timed_out=False,
        )


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=2.0)
    except TimeoutError:
        process.kill()
        await process.wait()


class GitWorktreeManager:
    """Create and remove detached Git worktrees at a pinned revision."""

    async def create(self, *, source_root: Path, revision: str, destination: Path) -> None:
        capture = await LocalCommandRunner().run(
            argv=(
                "git",
                "-C",
                str(source_root),
                "worktree",
                "add",
                "--detach",
                str(destination),
                revision,
            ),
            cwd=source_root,
            timeout_seconds=60.0,
        )
        if capture.exit_code != 0:
            raise RuntimeError(f"git worktree add failed: {capture.stderr[:500]}")

    async def release(self, *, source_root: Path, destination: Path) -> None:
        capture = await LocalCommandRunner().run(
            argv=("git", "-C", str(source_root), "worktree", "remove", "--force", str(destination)),
            cwd=source_root,
            timeout_seconds=60.0,
        )
        if capture.exit_code != 0:
            raise RuntimeError(f"git worktree remove failed: {capture.stderr[:500]}")

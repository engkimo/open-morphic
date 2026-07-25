"""Zero-cost rehearsal for the recorded agent CLI benchmark pipeline."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from benchmarks.agent_cli_adjudication import (
    AdjudicationReviews,
    RecordedEvidence,
    ReviewDecision,
    finalize_recorded_results,
)
from benchmarks.agent_cli_comparison import (
    SCHEMA_VERSION,
    AgentCliArm,
    AgentCliManifest,
    BenchmarkTask,
    RecordedResults,
)
from benchmarks.agent_cli_recorder import (
    AgentCliRecorderConfig,
    AgentCliTrialRecorder,
    CommandRunnerPort,
    GitWorktreeManager,
    LocalCommandRunner,
    WorktreeManagerPort,
)

DEFAULT_BENCHMARK_ID = "agent-cli-local-rehearsal"
DEFAULT_TASK_ID = "local-rehearsal"
DEFAULT_GOAL = "Exercise the recorded benchmark pipeline without external agents."


@dataclass(frozen=True)
class LocalRehearsalArtifacts:
    manifest: AgentCliManifest
    config: AgentCliRecorderConfig
    evidence: RecordedEvidence
    reviews: AdjudicationReviews
    results: RecordedResults


def _json_print_script(*payloads: dict[str, object]) -> str:
    statements = ["import json"]
    statements.extend(
        f"print(json.dumps({payload!r}, sort_keys=True))" for payload in payloads
    )
    return "; ".join(statements)


def build_local_rehearsal_contract(
    *,
    workspace_revision: str,
    python_executable: str = sys.executable,
    benchmark_id: str = DEFAULT_BENCHMARK_ID,
    task_id: str = DEFAULT_TASK_ID,
    goal: str = DEFAULT_GOAL,
) -> tuple[AgentCliManifest, AgentCliRecorderConfig]:
    """Build an internal-only three-arm contract whose maximum cost is zero."""
    manifest = AgentCliManifest(
        schema_version=SCHEMA_VERSION,
        benchmark_id=benchmark_id,
        task=BenchmarkTask(
            id=task_id,
            goal=goal,
            workspace_revision=workspace_revision,
            checks=("local_process",),
            handoff_assertions=("receipt_contract",),
        ),
        arms=tuple(AgentCliArm),
        repetitions=1,
    )
    codex = _json_print_script(
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
    )
    claude = _json_print_script(
        {"type": "system", "subtype": "init", "model": "local-rehearsal"},
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "ok",
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "total_cost_usd": 0.0,
        },
    )
    morphic = _json_print_script(
        {
            "type": "morphic_benchmark_receipt",
            "success": True,
            "model": "morphic-control[local-rehearsal]",
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "cost_usd": 0.0,
        }
    )
    success_command = (python_executable, "-c", "raise SystemExit(0)")
    config = AgentCliRecorderConfig(
        schema_version=SCHEMA_VERSION,
        benchmark_id=benchmark_id,
        arm_commands={
            AgentCliArm.CODEX_CLI: (python_executable, "-c", codex),
            AgentCliArm.CLAUDE_CODE: (python_executable, "-c", claude),
            AgentCliArm.MORPHIC_CONTROL: (python_executable, "-c", morphic),
        },
        check_commands={"local_process": success_command},
        handoff_commands={"receipt_contract": success_command},
        estimated_cost_usd_per_trial={arm: 0.0 for arm in AgentCliArm},
        model_hints={AgentCliArm.CODEX_CLI: "local-rehearsal"},
        timeout_seconds=10.0,
    )
    return manifest, config


async def run_local_rehearsal(
    *,
    source_root: Path,
    worktree_root: Path,
    workspace_revision: str,
    python_executable: str = sys.executable,
    worktree_manager: WorktreeManagerPort | None = None,
    command_runner: CommandRunnerPort | None = None,
) -> LocalRehearsalArtifacts:
    """Exercise recorder, receipts, review join, and finalizer without external agents."""
    manifest, config = build_local_rehearsal_contract(
        workspace_revision=workspace_revision,
        python_executable=python_executable,
    )
    recorded = await AgentCliTrialRecorder(
        worktree_manager=worktree_manager or GitWorktreeManager(),
        command_runner=command_runner or LocalCommandRunner(),
    ).record(
        manifest=manifest,
        config=config,
        source_root=source_root,
        worktree_root=worktree_root,
        acknowledged_paid=True,
        cost_cap_usd=0.0,
    )
    evidence = RecordedEvidence.model_validate(recorded.to_dict())
    decisions = tuple(
        ReviewDecision(
            arm=trial.arm,
            trial=trial.trial,
            agent_argv_sha256=trial.agent.argv_sha256,
            accepted_patch=False,
            human_interventions=0,
            recovery_attempted=False,
            recovery_succeeded=False,
            reviewer_id="local-rehearsal:no-human-review",
            review_artifact_sha256=hashlib.sha256(
                (
                    f"{manifest.benchmark_id}:{trial.arm.value}:{trial.trial}:"
                    f"{trial.agent.argv_sha256}:local-rehearsal"
                ).encode()
            ).hexdigest(),
        )
        for trial in evidence.trials
    )
    reviews = AdjudicationReviews(
        schema_version=SCHEMA_VERSION,
        benchmark_id=manifest.benchmark_id,
        task_id=manifest.task.id,
        workspace_revision=manifest.task.workspace_revision,
        decisions=decisions,
    )
    return LocalRehearsalArtifacts(
        manifest=manifest,
        config=config,
        evidence=evidence,
        reviews=reviews,
        results=finalize_recorded_results(manifest, evidence, reviews),
    )


def _model_json(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"


def publish_local_rehearsal(
    output_dir: Path,
    artifacts: LocalRehearsalArtifacts,
) -> None:
    """Publish a complete bundle into a newly-created directory only."""
    output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        payloads = {
            "manifest.json": _model_json(artifacts.manifest),
            "recorder-config.json": _model_json(artifacts.config),
            "evidence.json": _model_json(artifacts.evidence),
            "reviews.json": _model_json(artifacts.reviews),
            "results.json": _model_json(artifacts.results),
        }
        for name, payload in payloads.items():
            (output_dir / name).write_text(payload, encoding="utf-8")
    except Exception:
        shutil.rmtree(output_dir)
        raise


async def resolve_git_revision(
    source_root: Path,
    revision: str,
    *,
    command_runner: CommandRunnerPort | None = None,
) -> str:
    """Resolve a revision to a full immutable commit hash without a shell."""
    runner = command_runner or LocalCommandRunner()
    capture = await runner.run(
        argv=(
            "git",
            "-C",
            str(source_root.resolve()),
            "rev-parse",
            "--verify",
            f"{revision}^{{commit}}",
        ),
        cwd=source_root.resolve(),
        timeout_seconds=30.0,
    )
    resolved = capture.stdout.strip()
    if capture.exit_code != 0 or len(resolved) != 40:
        raise ValueError(f"cannot resolve Git revision {revision!r}")
    return resolved


if __name__ == "__main__":
    raise SystemExit("Use `morphic benchmark agent-cli-rehearse`.")

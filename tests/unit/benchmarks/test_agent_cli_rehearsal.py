"""Tests for zero-cost agent CLI benchmark rehearsal."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from benchmarks.agent_cli_comparison import AgentCliArm, AgentCliManifest
from benchmarks.agent_cli_recorder import AgentCliRecorderConfig, LocalCommandRunner
from benchmarks.agent_cli_rehearsal import (
    build_local_rehearsal_contract,
    publish_local_rehearsal,
    run_local_rehearsal,
)
from interface.cli.main import app

runner = CliRunner()


class _DirectoryWorktrees:
    async def create(self, *, source_root: Path, revision: str, destination: Path) -> None:
        del source_root, revision
        destination.mkdir(parents=True)

    async def release(self, *, source_root: Path, destination: Path) -> None:
        del source_root
        destination.rmdir()


def test_committed_dry_run_templates_validate() -> None:
    root = Path(__file__).parents[3]
    manifest_payload = json.loads(
        (root / "benchmarks/templates/agent_cli_manifest.example.json").read_text()
    )
    manifest_payload["task"]["workspace_revision"] = "a" * 40
    config_payload = json.loads(
        (root / "benchmarks/templates/agent_cli_recorder.example.json").read_text()
    )

    manifest = AgentCliManifest.model_validate(manifest_payload)
    example_config = AgentCliRecorderConfig.model_validate(config_payload)
    _, config = build_local_rehearsal_contract(
        workspace_revision=manifest.task.workspace_revision,
        python_executable=sys.executable,
        benchmark_id=manifest.benchmark_id,
        task_id=manifest.task.id,
        goal=manifest.task.goal,
    )

    assert set(config_payload["arm_commands"]) == {
        "codex_cli",
        "claude_code",
        "morphic_control",
    }
    assert set(example_config.estimated_cost_usd_per_trial.values()) == {0.0}
    assert config.benchmark_id == manifest.benchmark_id


def test_local_rehearsal_contract_is_internal_and_zero_cost() -> None:
    manifest, config = build_local_rehearsal_contract(
        workspace_revision="revision-43",
        python_executable=sys.executable,
    )

    assert manifest.repetitions == 1
    assert set(config.arm_commands) == set(AgentCliArm)
    assert set(config.estimated_cost_usd_per_trial.values()) == {0.0}
    assert all(command[:2] == (sys.executable, "-c") for command in config.arm_commands.values())
    assert all("codex" not in command[0] for command in config.arm_commands.values())
    assert all("claude" not in command[0] for command in config.arm_commands.values())


@pytest.mark.asyncio
async def test_local_rehearsal_runs_complete_pipeline_without_agent_processes(
    tmp_path: Path,
) -> None:
    artifacts = await run_local_rehearsal(
        source_root=tmp_path / "source",
        worktree_root=tmp_path / "worktrees",
        workspace_revision="revision-43",
        python_executable=sys.executable,
        worktree_manager=_DirectoryWorktrees(),
        command_runner=LocalCommandRunner(),
    )

    assert artifacts.evidence.cost_collection == "normalized_receipts"
    assert len(artifacts.evidence.trials) == 3
    assert {trial.receipt.cost_usd for trial in artifacts.evidence.trials if trial.receipt} == {
        0.0
    }
    assert len(artifacts.results.observations) == 3
    assert all(observation.completed for observation in artifacts.results.observations)
    assert not any(observation.accepted_patch for observation in artifacts.results.observations)
    assert not (tmp_path / "worktrees").exists() or not any(
        (tmp_path / "worktrees").iterdir()
    )


def test_local_rehearsal_publication_is_deterministic_and_exclusive(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError):
        publish_local_rehearsal(output, object())  # type: ignore[arg-type]

    assert marker.read_text(encoding="utf-8") == "preserve"


def test_agent_cli_rehearse_cli_refuses_existing_output() -> None:
    with runner.isolated_filesystem():
        output = Path("artifacts")
        output.mkdir()
        result = runner.invoke(
            app,
            ["benchmark", "agent-cli-rehearse", "--output-dir", str(output)],
        )

    assert result.exit_code == 1
    assert "already exists" in result.output

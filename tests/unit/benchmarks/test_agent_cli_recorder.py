"""Tests for the opt-in isolated agent CLI trial recorder."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from benchmarks.agent_cli_comparison import AgentCliManifest
from benchmarks.agent_cli_receipts import ProviderReceipt
from benchmarks.agent_cli_recorder import (
    AgentCliRecorderConfig,
    AgentCliTrialRecorder,
    CommandCapture,
    GitWorktreeManager,
    LocalCommandRunner,
    build_recording_plan,
    validate_execution_consent,
)
from interface.cli.commands.benchmark import _write_new_evidence
from interface.cli.main import app

runner = CliRunner()


def _manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "benchmark_id": "record-001",
        "task": {
            "id": "task-001",
            "goal": "Implement one isolated change",
            "workspace_revision": "abc123",
            "checks": ["unit"],
            "handoff_assertions": ["decision"],
        },
        "arms": ["codex_cli", "claude_code", "morphic_control"],
        "repetitions": 1,
    }


def _config() -> dict[str, object]:
    return {
        "schema_version": 1,
        "benchmark_id": "record-001",
        "arm_commands": {
            "codex_cli": ["codex", "{goal}"],
            "claude_code": ["claude", "{goal}"],
            "morphic_control": ["morphic", "code", "{goal}"],
        },
        "check_commands": {"unit": ["verify", "unit"]},
        "handoff_commands": {"decision": ["verify", "decision"]},
        "estimated_cost_usd_per_trial": {
            "codex_cli": 0.1,
            "claude_code": 0.2,
            "morphic_control": 0.3,
        },
        "timeout_seconds": 60.0,
    }


class FakeWorktrees:
    def __init__(self) -> None:
        self.created: list[tuple[Path, str, Path]] = []
        self.released: list[Path] = []

    async def create(self, *, source_root: Path, revision: str, destination: Path) -> None:
        self.created.append((source_root, revision, destination))
        destination.mkdir(parents=True)

    async def release(self, *, source_root: Path, destination: Path) -> None:
        self.released.append(destination)


class FakeCommands:
    def __init__(self, *, fail_with: Exception | None = None) -> None:
        self.calls: list[tuple[tuple[str, ...], Path, float]] = []
        self.fail_with = fail_with

    async def run(
        self,
        *,
        argv: tuple[str, ...],
        cwd: Path,
        timeout_seconds: float,
    ) -> CommandCapture:
        self.calls.append((argv, cwd, timeout_seconds))
        if self.fail_with is not None:
            raise self.fail_with
        return CommandCapture(
            exit_code=0,
            stdout="secret output",
            stderr="secret warning",
            elapsed_seconds=1.25,
            timed_out=False,
        )


class FakeReceipts:
    def parse(
        self,
        *,
        arm: object,
        stdout: str,
        model_hint: str | None = None,
    ) -> ProviderReceipt:
        return ProviderReceipt(
            provider=getattr(arm, "value", arm),
            success=True,
            model=model_hint or "test-model",
            usage={"input_tokens": 10, "output_tokens": 2},
            cost_usd=(0.00006 if getattr(arm, "value", arm) == "codex_cli" else 0.01),
            cost_source={
                "codex_cli": "calculated_from_usage",
                "claude_code": "provider_reported",
                "morphic_control": "morphic_reported",
            }[getattr(arm, "value", arm)],
        )


def test_build_recording_plan_is_deterministic_and_reserves_cost() -> None:
    manifest = AgentCliManifest.model_validate(_manifest())
    config = AgentCliRecorderConfig.model_validate(_config())

    first = build_recording_plan(manifest, config).to_json()
    second = build_recording_plan(manifest, config).to_json()
    payload = json.loads(first)

    assert first == second
    assert payload["trial_count"] == 3
    assert payload["estimated_max_cost_usd"] == 0.6
    assert payload["execution_required"] is False
    assert "Implement one isolated change" not in first
    assert "timestamp" not in payload


@pytest.mark.parametrize(
    ("acknowledged_paid", "cost_cap_usd", "match"),
    [
        (False, 1.0, "acknowledgement"),
        (True, None, "cost cap"),
        (True, 0.59, "below estimated"),
    ],
)
def test_execution_consent_fails_closed(
    acknowledged_paid: bool,
    cost_cap_usd: float | None,
    match: str,
) -> None:
    plan = build_recording_plan(
        AgentCliManifest.model_validate(_manifest()),
        AgentCliRecorderConfig.model_validate(_config()),
    )

    with pytest.raises(ValueError, match=match):
        validate_execution_consent(
            plan,
            acknowledged_paid=acknowledged_paid,
            cost_cap_usd=cost_cap_usd,
        )


def test_config_requires_exact_declared_arms_checks_and_handoffs() -> None:
    manifest = AgentCliManifest.model_validate(_manifest())
    raw = _config()
    del raw["arm_commands"]["claude_code"]  # type: ignore[index]

    with pytest.raises(ValueError, match="arm_commands"):
        build_recording_plan(manifest, AgentCliRecorderConfig.model_validate(raw))

    raw = _config()
    raw["check_commands"] = {"other": ["verify"]}
    with pytest.raises(ValueError, match="check_commands"):
        build_recording_plan(manifest, AgentCliRecorderConfig.model_validate(raw))


@pytest.mark.asyncio
async def test_recorder_isolates_trials_and_hashes_raw_output(tmp_path: Path) -> None:
    worktrees = FakeWorktrees()
    commands = FakeCommands()
    recorder = AgentCliTrialRecorder(worktree_manager=worktrees, command_runner=commands)

    evidence = await recorder.record(
        manifest=AgentCliManifest.model_validate(_manifest()),
        config=AgentCliRecorderConfig.model_validate(_config()),
        source_root=tmp_path / "source",
        worktree_root=tmp_path / "worktrees",
        acknowledged_paid=True,
        cost_cap_usd=0.6,
    )
    payload = evidence.to_dict()

    assert len(worktrees.created) == 3
    assert len({item[2] for item in worktrees.created}) == 3
    assert worktrees.released == [item[2] for item in worktrees.created]
    assert len(payload["trials"]) == 3
    assert payload["authorized_cost_cap_usd"] == 0.6
    assert payload["trials"][0]["passed_checks"] == ["unit"]
    assert payload["trials"][0]["passed_handoff_assertions"] == ["decision"]
    assert "secret output" not in evidence.to_json()
    assert "secret warning" not in evidence.to_json()
    assert payload["trials"][0]["agent"]["stdout_bytes"] == 13
    assert len(payload["trials"][0]["agent"]["stdout_sha256"]) == 64
    assert payload["cost_collection"] == "pending_adjudication"


@pytest.mark.asyncio
async def test_recorder_normalizes_all_receipts_before_discarding_output(tmp_path: Path) -> None:
    recorder = AgentCliTrialRecorder(
        worktree_manager=FakeWorktrees(),
        command_runner=FakeCommands(),
        receipt_parser=FakeReceipts(),
    )

    evidence = await recorder.record(
        manifest=AgentCliManifest.model_validate(_manifest()),
        config=AgentCliRecorderConfig.model_validate(_config()),
        source_root=tmp_path / "source",
        worktree_root=tmp_path / "worktrees",
        acknowledged_paid=True,
        cost_cap_usd=0.6,
    )
    payload = evidence.to_dict()

    assert payload["cost_collection"] == "normalized_receipts"
    assert payload["trials"][0]["receipt"]["cost_usd"] == 0.00006
    assert "secret output" not in evidence.to_json()


@pytest.mark.asyncio
async def test_recorder_releases_worktree_when_command_raises(tmp_path: Path) -> None:
    worktrees = FakeWorktrees()
    recorder = AgentCliTrialRecorder(
        worktree_manager=worktrees,
        command_runner=FakeCommands(fail_with=RuntimeError("runner failed")),
    )

    with pytest.raises(RuntimeError, match="runner failed"):
        await recorder.record(
            manifest=AgentCliManifest.model_validate(_manifest()),
            config=AgentCliRecorderConfig.model_validate(_config()),
            source_root=tmp_path / "source",
            worktree_root=tmp_path / "worktrees",
            acknowledged_paid=True,
            cost_cap_usd=0.6,
        )

    assert len(worktrees.created) == 1
    assert worktrees.released == [worktrees.created[0][2]]


@pytest.mark.asyncio
async def test_recorder_refuses_worktrees_inside_source(tmp_path: Path) -> None:
    recorder = AgentCliTrialRecorder(
        worktree_manager=FakeWorktrees(),
        command_runner=FakeCommands(),
    )
    source_root = tmp_path / "source"

    with pytest.raises(ValueError, match="outside source_root"):
        await recorder.record(
            manifest=AgentCliManifest.model_validate(_manifest()),
            config=AgentCliRecorderConfig.model_validate(_config()),
            source_root=source_root,
            worktree_root=source_root / ".morphic" / "worktrees",
            acknowledged_paid=True,
            cost_cap_usd=0.6,
        )

    assert not (source_root / ".morphic").exists()


@pytest.mark.asyncio
async def test_local_runner_passes_arguments_without_a_shell(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    literal = f"$(touch {marker})"

    capture = await LocalCommandRunner().run(
        argv=(sys.executable, "-c", "import sys; print(sys.argv[1])", literal),
        cwd=tmp_path,
        timeout_seconds=5.0,
    )

    assert capture.exit_code == 0
    assert capture.stdout.strip() == literal
    assert not marker.exists()


@pytest.mark.asyncio
async def test_git_worktree_manager_creates_pinned_detached_workspace(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    command_runner = LocalCommandRunner()

    async def git(*args: str, cwd: Path = source) -> CommandCapture:
        capture = await command_runner.run(
            argv=("git", *args),
            cwd=cwd,
            timeout_seconds=10.0,
        )
        assert capture.exit_code == 0, capture.stderr
        return capture

    await git("init")
    await git("config", "user.email", "benchmark@example.invalid")
    await git("config", "user.name", "Benchmark Test")
    (source / "evidence.txt").write_text("pinned", encoding="utf-8")
    await git("add", "evidence.txt")
    await git("commit", "-m", "Create pinned revision")
    revision = (await git("rev-parse", "HEAD")).stdout.strip()
    destination = tmp_path / "worktrees" / "trial"
    destination.parent.mkdir()
    manager = GitWorktreeManager()

    await manager.create(source_root=source, revision=revision, destination=destination)

    assert (destination / "evidence.txt").read_text(encoding="utf-8") == "pinned"
    assert (await git("rev-parse", "HEAD", cwd=destination)).stdout.strip() == revision

    await manager.release(source_root=source, destination=destination)
    assert not destination.exists()


def test_evidence_publish_is_exclusive_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    _write_new_evidence(evidence, "first")

    with pytest.raises(FileExistsError):
        _write_new_evidence(evidence, "second")

    assert evidence.read_text(encoding="utf-8") == "first"
    assert list(tmp_path.glob(".evidence.json.*.tmp")) == []


def test_cli_defaults_to_plan_without_creating_worktrees(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    config_path = tmp_path / "recorder.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    config_path.write_text(json.dumps(_config()), encoding="utf-8")
    worktree_root = tmp_path / "worktrees"

    result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-record",
            "--manifest",
            str(manifest_path),
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["execution_required"] is False
    assert not worktree_root.exists()


def test_cli_rejects_execute_without_paid_acknowledgement(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    config_path = tmp_path / "recorder.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    config_path.write_text(json.dumps(_config()), encoding="utf-8")
    worktree_root = tmp_path / "worktrees"

    result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-record",
            "--manifest",
            str(manifest_path),
            "--config",
            str(config_path),
            "--worktree-root",
            str(worktree_root),
            "--execute",
            "--cost-cap-usd",
            "1.0",
        ],
    )

    assert result.exit_code == 2
    assert "acknowledgement" in result.output
    assert not worktree_root.exists()

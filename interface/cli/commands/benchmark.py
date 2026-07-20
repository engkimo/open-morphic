"""CLI commands for benchmarks — Sprint 7.6."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import typer

from interface.cli.formatters import console

benchmark_app = typer.Typer(no_args_is_help=True)
_AGENT_CLI_MANIFEST_OPTION = typer.Option(
    ...,
    "--manifest",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Same-task benchmark manifest JSON.",
)
_AGENT_CLI_RESULTS_OPTION = typer.Option(
    ...,
    "--results",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Recorded trial observations JSON.",
)
_AGENT_CLI_JSON_OPTION = typer.Option(False, "--json", help="Emit deterministic JSON.")
_RECORDER_CONFIG_OPTION = typer.Option(
    ...,
    "--config",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Recorder command configuration JSON.",
)
_RECORDER_WORKTREE_OPTION = typer.Option(None, "--worktree-root", help="Isolated worktree root.")
_RECORDER_SOURCE_OPTION = typer.Option(None, "--source-root", help="Source Git workspace.")
_RECORDER_EVIDENCE_OPTION = typer.Option(None, "--evidence", help="Evidence JSON output path.")
_RECORDER_EXECUTE_OPTION = typer.Option(False, "--execute", help="Execute the recorded plan.")
_RECORDER_ACK_OPTION = typer.Option(
    False,
    "--acknowledge-paid",
    help="Acknowledge that configured commands may incur charges.",
)
_RECORDER_COST_CAP_OPTION = typer.Option(
    None,
    "--cost-cap-usd",
    help="Explicit cap that must cover the configured maximum estimate.",
)
_FINALIZE_EVIDENCE_OPTION = typer.Option(
    ...,
    "--evidence",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Normalized recorder evidence JSON.",
)
_FINALIZE_REVIEWS_OPTION = typer.Option(
    ...,
    "--reviews",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Independent adjudication reviews JSON.",
)
_FINALIZE_OUTPUT_OPTION = typer.Option(None, "--output", help="Final Phase 40 results path.")


def _write_new_evidence(path: Path, payload: str) -> None:
    """Publish evidence atomically without replacing an existing path."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.link(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _get_container() -> Any:
    from interface.cli._utils import _get_container as _gc

    return _gc()


def _run(coro: Any) -> Any:
    from interface.cli._utils import _run as _r

    return _r(coro)


@benchmark_app.command("run")
def run_all() -> None:
    """Run all benchmarks (context continuity + dedup accuracy)."""
    from benchmarks.runner import run_all as _run_all

    container = _get_container()
    adapters = container._context_adapters
    result = _run(_run_all(adapters))

    # Context continuity
    if result.context_continuity:
        console.print("\n[bold]Context Continuity Benchmark[/bold]")
        from rich.table import Table

        table = Table(show_header=True)
        table.add_column("Engine", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("Decisions", justify="right")
        table.add_column("Artifacts", justify="right")
        table.add_column("Blockers", justify="right")
        table.add_column("Length", justify="right")

        for s in result.context_continuity.adapter_scores:
            score_style = "green" if s.score >= 0.85 else "yellow" if s.score >= 0.5 else "red"
            table.add_row(
                s.engine,
                f"[{score_style}]{s.score:.0%}[/{score_style}]",
                f"{s.decisions_found}/{s.decisions_injected}",
                f"{s.artifacts_found}/{s.artifacts_injected}",
                f"{s.blockers_found}/{s.blockers_injected}",
                str(s.context_length),
            )
        console.print(table)
        overall = result.context_continuity.overall_score
        style = "green" if overall >= 0.85 else "yellow"
        console.print(f"  Overall: [{style}]{overall:.0%}[/{style}]")

    # Dedup accuracy
    if result.dedup_accuracy:
        console.print("\n[bold]Memory Dedup Benchmark[/bold]")
        from rich.table import Table

        table = Table(show_header=True)
        table.add_column("Scenario", style="cyan")
        table.add_column("Dedup Rate", justify="right")
        table.add_column("Raw", justify="right")
        table.add_column("Unique", justify="right")

        for s in result.dedup_accuracy.scores:
            rate_style = "green" if s.dedup_rate >= 0.5 else "yellow"
            table.add_row(
                s.scenario,
                f"[{rate_style}]{s.dedup_rate:.0%}[/{rate_style}]",
                str(s.total_raw),
                str(s.deduped_count),
            )
        console.print(table)
        accuracy = result.dedup_accuracy.overall_accuracy
        style = "green" if accuracy >= 0.5 else "yellow"
        console.print(f"  Overall: [{style}]{accuracy:.0%}[/{style}]")

    # Errors
    if result.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for err in result.errors:
            console.print(f"  [red]• {err}[/red]")

    # Summary
    console.print(f"\n[bold]Overall Score: {result.overall_score:.0%}[/bold]")
    if result.overall_score >= 0.85:
        console.print("[green]✓ Benchmark threshold (85%) passed[/green]")
    else:
        console.print("[yellow]⚠ Below 85% threshold[/yellow]")


@benchmark_app.command("continuity")
def run_continuity() -> None:
    """Run context continuity benchmark only."""
    from benchmarks.context_continuity import run_benchmark

    container = _get_container()
    adapters = container._context_adapters
    result = run_benchmark(adapters)

    console.print(f"\n[bold]Context Continuity: {result.overall_score:.0%}[/bold]")
    for s in result.adapter_scores:
        style = "green" if s.score >= 0.85 else "yellow" if s.score >= 0.5 else "red"
        console.print(f"  {s.engine:<15} [{style}]{s.score:.0%}[/{style}]")


@benchmark_app.command("dedup")
def run_dedup() -> None:
    """Run memory dedup accuracy benchmark only."""
    from benchmarks.dedup_accuracy import run_benchmark

    container = _get_container()
    adapters = container._context_adapters
    result = _run(run_benchmark(adapters))

    console.print(f"\n[bold]Dedup Accuracy: {result.overall_accuracy:.0%}[/bold]")
    for s in result.scores:
        style = "green" if s.dedup_rate >= 0.5 else "yellow"
        console.print(f"  {s.scenario:<25} [{style}]{s.dedup_rate:.0%}[/{style}]")


@benchmark_app.command("agent-cli")
def compare_agent_clis(
    manifest_path: Path = _AGENT_CLI_MANIFEST_OPTION,
    results_path: Path = _AGENT_CLI_RESULTS_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Compare recorded Codex, Claude Code, and Morphic-controlled trials."""
    from benchmarks.agent_cli_comparison import (
        AgentCliManifest,
        RecordedResults,
        evaluate_recorded_results,
    )

    try:
        manifest = AgentCliManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        results = RecordedResults.model_validate_json(results_path.read_text(encoding="utf-8"))
        report = evaluate_recorded_results(manifest, results)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Invalid agent CLI benchmark input: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        console.print(report.to_json(), markup=False)
        return

    from rich.table import Table

    table = Table(title=f"Agent CLI Same-task Benchmark: {report.benchmark_id}")
    table.add_column("Arm", style="cyan")
    table.add_column("Complete", justify="right")
    table.add_column("Accepted", justify="right")
    table.add_column("Verified", justify="right")
    table.add_column("Median sec", justify="right")
    table.add_column("Mean USD", justify="right")
    table.add_column("Interventions", justify="right")
    table.add_column("Recovery", justify="right")
    table.add_column("Handoff", justify="right")
    for arm, metrics in report.arms.items():
        recovery = "n/a" if metrics.recovery_rate is None else f"{metrics.recovery_rate:.0%}"
        table.add_row(
            arm,
            f"{metrics.completion_rate:.0%}",
            f"{metrics.accepted_patch_rate:.0%}",
            f"{metrics.verification_rate:.0%}",
            f"{metrics.median_elapsed_seconds:.1f}",
            f"{metrics.mean_cost_usd:.4f}",
            f"{metrics.mean_human_interventions:.2f}",
            recovery,
            f"{metrics.context_handoff_score:.0%}",
        )
    console.print(table)
    console.print("[bold]Metric leaders[/bold]")
    for metric, leaders in report.leaders.items():
        names = ", ".join(leaders) if leaders else "n/a"
        console.print(f"  {metric}: {names}")
    console.print("[dim]No composite score; metric leaders are reported independently.[/dim]")


@benchmark_app.command("agent-cli-record")
def record_agent_cli_trials(
    manifest_path: Path = _AGENT_CLI_MANIFEST_OPTION,
    config_path: Path = _RECORDER_CONFIG_OPTION,
    worktree_root: Path | None = _RECORDER_WORKTREE_OPTION,
    source_root: Path | None = _RECORDER_SOURCE_OPTION,
    evidence_path: Path | None = _RECORDER_EVIDENCE_OPTION,
    execute: bool = _RECORDER_EXECUTE_OPTION,
    acknowledge_paid: bool = _RECORDER_ACK_OPTION,
    cost_cap_usd: float | None = _RECORDER_COST_CAP_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Plan or explicitly execute isolated same-task CLI trials."""
    from benchmarks.agent_cli_comparison import AgentCliManifest
    from benchmarks.agent_cli_recorder import (
        AgentCliRecorderConfig,
        AgentCliTrialRecorder,
        GitWorktreeManager,
        LocalCommandRunner,
        build_recording_plan,
        validate_execution_consent,
    )

    try:
        manifest = AgentCliManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        config = AgentCliRecorderConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
        plan = build_recording_plan(manifest, config)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Invalid agent CLI recorder input: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if not execute:
        if as_json:
            typer.echo(plan.to_json())
        else:
            console.print(
                f"Recorder plan trials={plan.trial_count} "
                f"estimated_max=${plan.estimated_max_cost_usd:.6f} execute=false"
            )
        return

    try:
        validate_execution_consent(
            plan,
            acknowledged_paid=acknowledge_paid,
            cost_cap_usd=cost_cap_usd,
        )
        if worktree_root is None:
            raise ValueError("--worktree-root is required with --execute")
        if evidence_path is None:
            raise ValueError("--evidence is required with --execute")
        if not evidence_path.parent.exists():
            raise ValueError("evidence output parent must already exist")
        if evidence_path.exists():
            raise ValueError("evidence output already exists")
    except ValueError as exc:
        console.print(f"[red]Recorder execution refused: {exc}[/red]")
        raise typer.Exit(code=2) from None

    recorder = AgentCliTrialRecorder(
        worktree_manager=GitWorktreeManager(),
        command_runner=LocalCommandRunner(),
    )
    try:
        evidence = _run(
            recorder.record(
                manifest=manifest,
                config=config,
                source_root=(source_root or Path.cwd()).resolve(),
                worktree_root=worktree_root.resolve(),
                acknowledged_paid=acknowledge_paid,
                cost_cap_usd=cost_cap_usd,
            )
        )
        _write_new_evidence(evidence_path, evidence.to_json())
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]Recorder execution failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(evidence.to_json())
    else:
        console.print(f"Recorded {len(evidence.trials)} isolated trials to {evidence_path}")


@benchmark_app.command("agent-cli-finalize")
def finalize_agent_cli_trials(
    manifest_path: Path = _AGENT_CLI_MANIFEST_OPTION,
    evidence_path: Path = _FINALIZE_EVIDENCE_OPTION,
    reviews_path: Path = _FINALIZE_REVIEWS_OPTION,
    output_path: Path | None = _FINALIZE_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Join normalized receipts and reviews into Phase 40 observations."""
    from benchmarks.agent_cli_adjudication import (
        AdjudicationReviews,
        RecordedEvidence,
        finalize_recorded_results,
        finalized_results_json,
    )
    from benchmarks.agent_cli_comparison import AgentCliManifest

    try:
        manifest = AgentCliManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        evidence = RecordedEvidence.model_validate_json(evidence_path.read_text(encoding="utf-8"))
        reviews = AdjudicationReviews.model_validate_json(reviews_path.read_text(encoding="utf-8"))
        results = finalize_recorded_results(manifest, evidence, reviews)
        payload = finalized_results_json(results)
        if output_path is not None:
            if not output_path.parent.exists():
                raise ValueError("output parent must already exist")
            if output_path.exists():
                raise ValueError("output already exists")
            _write_new_evidence(output_path, payload)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI adjudication failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(payload)
    else:
        console.print(f"Finalized {len(results.observations)} benchmark observations")

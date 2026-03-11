"""CLI commands for benchmarks — Sprint 7.6."""

from __future__ import annotations

from typing import Any

import typer

from interface.cli.formatters import console

benchmark_app = typer.Typer(no_args_is_help=True)


def _get_container() -> Any:
    from interface.cli.main import _get_container

    return _get_container()


def _run(coro: Any) -> Any:
    from interface.cli.main import _run

    return _run(coro)


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

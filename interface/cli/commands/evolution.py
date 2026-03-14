"""Evolution subcommands — stats, failures, update, report."""

from __future__ import annotations

import typer

from interface.cli._utils import _get_container, _run
from interface.cli.formatters import console, print_error

evolution_app = typer.Typer()


@evolution_app.command("stats")
def stats(
    task_type: str | None = typer.Option(None, "--type", "-t", help="Filter by task type."),
) -> None:
    """Show execution statistics."""
    c = _get_container()
    tt = None
    if task_type:
        from domain.value_objects.model_tier import TaskType

        try:
            tt = TaskType(task_type)
        except ValueError:
            print_error(f"Unknown task type: {task_type}")
            raise typer.Exit(code=1) from None

    result = _run(c.analyze_execution.get_stats(task_type=tt))
    from rich.table import Table

    table = Table(title="Execution Statistics")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Total executions", str(result.total_count))
    table.add_row("Successes", f"[green]{result.success_count}[/]")
    table.add_row("Failures", f"[red]{result.failure_count}[/]")
    rate_style = (
        "green" if result.success_rate >= 0.8 else "yellow" if result.success_rate >= 0.5 else "red"
    )
    table.add_row("Success rate", f"[{rate_style}]{result.success_rate:.0%}[/]")
    table.add_row("Avg cost", f"${result.avg_cost_usd:.4f}")
    table.add_row("Avg duration", f"{result.avg_duration_seconds:.1f}s")
    console.print(table)

    if result.model_distribution:
        console.print("\n[bold]Model distribution:[/]")
        for model, count in sorted(result.model_distribution.items(), key=lambda x: -x[1]):
            console.print(f"  {model}: {count}")

    if result.engine_distribution:
        console.print("\n[bold]Engine distribution:[/]")
        for engine, count in sorted(result.engine_distribution.items(), key=lambda x: -x[1]):
            console.print(f"  {engine}: {count}")


@evolution_app.command("failures")
def failures(
    limit: int = typer.Option(20, "--limit", "-n", help="Max patterns to show."),
) -> None:
    """Show recent failure patterns."""
    c = _get_container()
    patterns = _run(c.analyze_execution.get_failure_patterns(limit=limit))
    if not patterns:
        console.print("[dim]No failure patterns found.[/]")
        return

    from rich.table import Table

    table = Table(title="Failure Patterns")
    table.add_column("Error", min_width=30)
    table.add_column("Count", justify="right")
    table.add_column("Task Types")
    table.add_column("Engines")
    for p in patterns:
        table.add_row(
            p.error_pattern[:60],
            f"[red]{p.count}[/]",
            ", ".join(p.task_types),
            ", ".join(p.engines),
        )
    console.print(table)


@evolution_app.command("update")
def update() -> None:
    """Run Level 2 strategy update (model/engine preferences + recovery rules)."""
    c = _get_container()
    with console.status("[blue]Updating strategies...[/]"):
        result = _run(c.update_strategy.run_full_update())
    console.print("[green]Strategy update complete.[/]")
    console.print(f"  Model preferences updated: {result.model_preferences_updated}")
    console.print(f"  Engine preferences updated: {result.engine_preferences_updated}")
    console.print(f"  Recovery rules added: {result.recovery_rules_added}")
    for detail in result.details:
        console.print(f"  [dim]{detail}[/]")


@evolution_app.command("report")
def report() -> None:
    """Run full Level 3 evolution and show report."""
    c = _get_container()
    with console.status("[blue]Running evolution...[/]"):
        result = _run(c.systemic_evolution.run_evolution())
    console.print(f"[bold]Evolution Report[/] ({result.level.value})")
    console.print(f"  Summary: {result.summary}")
    console.print(f"  Tool gaps found: {result.tool_gaps_found}")
    if result.tools_suggested:
        console.print(f"  Tools suggested: {', '.join(result.tools_suggested)}")
    if result.strategy_update:
        su = result.strategy_update
        console.print(f"  Model prefs: {su.model_preferences_updated}")
        console.print(f"  Engine prefs: {su.engine_preferences_updated}")
        console.print(f"  Recovery rules: {su.recovery_rules_added}")

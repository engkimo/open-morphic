"""Fallback strategy inspection CLI — execution history, failures, and stats."""

from __future__ import annotations

import typer

from interface.cli._utils import _get_container, _run
from interface.cli.formatters import (
    console,
    print_error,
    print_execution_history_table,
    print_execution_stats,
)

fallback_app = typer.Typer()


@fallback_app.command("history")
def history_cmd(
    task_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by task type (e.g. simple_qa, code_generation)",
    ),
    limit: int = typer.Option(50, "--limit", "-n", help="Max records"),
) -> None:
    """Show recent execution history with engine routing details."""
    from domain.value_objects.model_tier import TaskType

    c = _get_container()

    if task_type:
        try:
            tt = TaskType(task_type)
        except ValueError:
            valid = ", ".join(t.value for t in TaskType)
            print_error(f"Unknown task type: {task_type}. Valid: {valid}")
            raise typer.Exit(code=1) from None
        records = _run(c.execution_record_repo.list_by_task_type(tt, limit=limit))
    else:
        records = _run(c.execution_record_repo.list_recent(limit=limit))

    if not records:
        console.print("[dim]No execution records found.[/dim]")
        return

    print_execution_history_table(records)


@fallback_app.command("failures")
def failures_cmd(
    since: str | None = typer.Option(
        None,
        "--since",
        "-s",
        help="Show failures since date (YYYY-MM-DD)",
    ),
    limit: int = typer.Option(50, "--limit", "-n", help="Max records"),
) -> None:
    """Show failed executions for debugging fallback behavior."""
    from datetime import datetime

    c = _get_container()

    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            print_error(f"Invalid date format: {since}. Use YYYY-MM-DD")
            raise typer.Exit(code=1) from None

    records = _run(c.execution_record_repo.list_failures(since=since_dt))
    records = records[:limit]

    if not records:
        msg = "No failed executions found"
        if since:
            msg += f" since {since}"
        console.print(f"[dim]{msg}.[/dim]")
        return

    console.print(f"[bold red]Failed Executions ({len(records)})[/]\n")
    print_execution_history_table(records)


@fallback_app.command("stats")
def stats_cmd(
    task_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter stats by task type",
    ),
) -> None:
    """Show aggregated execution statistics — success rates, engine/model distribution."""
    from domain.value_objects.model_tier import TaskType

    c = _get_container()

    tt = None
    if task_type:
        try:
            tt = TaskType(task_type)
        except ValueError:
            valid = ", ".join(t.value for t in TaskType)
            print_error(f"Unknown task type: {task_type}. Valid: {valid}")
            raise typer.Exit(code=1) from None

    stats = _run(c.execution_record_repo.get_stats(task_type=tt))
    print_execution_stats(stats)

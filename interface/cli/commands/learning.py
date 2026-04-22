"""Learning repository CLI — fractal engine error patterns and successful paths."""

from __future__ import annotations

import typer

from interface.cli._utils import _get_container, _run
from interface.cli.formatters import (
    console,
    print_error,
    print_error_pattern_table,
    print_learning_stats,
    print_successful_path_table,
)

learning_app = typer.Typer()


@learning_app.command("list")
def list_cmd(
    kind: str = typer.Option(
        "all",
        "--kind",
        "-k",
        help="What to list: errors, successes, or all",
    ),
    limit: int = typer.Option(50, "--limit", "-n", help="Max entries"),
) -> None:
    """List learned error patterns and/or successful paths."""
    c = _get_container()
    repo = c.learning_repo
    if repo is None:
        print_error("Learning repository not available")
        raise typer.Exit(code=1)

    if kind in ("errors", "all"):
        patterns = _run(repo.list_error_patterns(limit=limit))
        if patterns:
            print_error_pattern_table(patterns)
        elif kind == "errors":
            console.print("[dim]No error patterns recorded.[/dim]")

    if kind in ("successes", "all"):
        paths = _run(repo.list_successful_paths(limit=limit))
        if paths:
            print_successful_path_table(paths)
        elif kind == "successes":
            console.print("[dim]No successful paths recorded.[/dim]")

    if kind == "all":
        patterns = _run(repo.list_error_patterns(limit=limit))
        paths = _run(repo.list_successful_paths(limit=limit))
        if not patterns and not paths:
            console.print("[dim]No learning data recorded yet.[/dim]")


@learning_app.command("search")
def search_cmd(
    goal: str = typer.Argument(..., help="Goal text to search for"),
) -> None:
    """Search learning data by goal (n-gram matching)."""
    c = _get_container()
    repo = c.learning_repo
    if repo is None:
        print_error("Learning repository not available")
        raise typer.Exit(code=1)

    patterns = _run(repo.find_error_patterns_by_goal(goal))
    paths = _run(repo.find_successful_paths(goal))

    if not patterns and not paths:
        console.print(f"[dim]No learning data matching '{goal}'.[/dim]")
        return

    if patterns:
        console.print(f"\n[bold]Error Patterns matching:[/] {goal}")
        print_error_pattern_table(patterns)

    if paths:
        console.print(f"\n[bold]Successful Paths matching:[/] {goal}")
        print_successful_path_table(paths)


@learning_app.command("stats")
def stats_cmd() -> None:
    """Show learning data statistics."""
    c = _get_container()
    repo = c.learning_repo
    if repo is None:
        print_error("Learning repository not available")
        raise typer.Exit(code=1)

    patterns = _run(repo.list_error_patterns(limit=10_000))
    paths = _run(repo.list_successful_paths(limit=10_000))

    print_learning_stats(patterns, paths)

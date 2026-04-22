"""Memory CLI commands — list, search, show, stats, and delete memory entries."""

from __future__ import annotations

import typer

from interface.cli._utils import _get_container, _run
from interface.cli.formatters import (
    console,
    print_error,
    print_memory_detail,
    print_memory_stats,
    print_memory_table,
)

memory_app = typer.Typer()


@memory_app.command("list")
def list_cmd(
    memory_type: str | None = typer.Option(
        None, "--type", "-t", help="Filter by type: l1_active, l2_semantic, l3_facts, l4_cold"
    ),
    limit: int = typer.Option(50, "--limit", "-n", help="Max entries to return"),
) -> None:
    """List memory entries, optionally filtered by type."""
    from domain.value_objects.status import MemoryType

    c = _get_container()

    if memory_type:
        try:
            mt = MemoryType(memory_type)
        except ValueError:
            valid = ", ".join(m.value for m in MemoryType)
            print_error(f"Unknown memory type: {memory_type}. Valid: {valid}")
            raise typer.Exit(code=1) from None
        entries = _run(c.memory_repo.list_by_type(mt, limit=limit))
    else:
        # Fetch all types
        entries = []
        for mt in MemoryType:
            entries.extend(_run(c.memory_repo.list_by_type(mt, limit=limit)))
        entries.sort(key=lambda e: e.last_accessed, reverse=True)
        entries = entries[:limit]

    if not entries:
        console.print("[dim]No memory entries found.[/dim]")
        return

    print_memory_table(entries)


@memory_app.command("search")
def search_cmd(
    query: str = typer.Argument(..., help="Search query (keyword or semantic)"),
    top_k: int = typer.Option(10, "--top-k", "-k", help="Max results"),
) -> None:
    """Search memory entries by keyword or semantic similarity."""
    c = _get_container()

    with console.status("[blue]Searching...[/]"):
        entries = _run(c.memory_repo.search(query, top_k=top_k))

    if not entries:
        console.print(f"[dim]No results for '{query}'.[/dim]")
        return

    console.print(f"[bold]Results for:[/] {query}\n")
    print_memory_table(entries)


@memory_app.command("show")
def show_cmd(
    memory_id: str = typer.Argument(..., help="Memory entry ID"),
) -> None:
    """Show details of a single memory entry."""
    c = _get_container()
    entry = _run(c.memory_repo.get_by_id(memory_id))

    if entry is None:
        print_error(f"Memory entry not found: {memory_id}")
        raise typer.Exit(code=1)

    print_memory_detail(entry)


@memory_app.command("stats")
def stats_cmd() -> None:
    """Show memory statistics — counts, types, access patterns."""
    from domain.value_objects.status import MemoryType

    c = _get_container()

    type_counts: dict[str, int] = {}
    total_entries = 0
    total_access = 0
    max_importance = 0.0

    for mt in MemoryType:
        entries = _run(c.memory_repo.list_by_type(mt, limit=10_000))
        count = len(entries)
        type_counts[mt.value] = count
        total_entries += count
        for e in entries:
            total_access += e.access_count
            if e.importance_score > max_importance:
                max_importance = e.importance_score

    print_memory_stats(
        type_counts=type_counts,
        total_entries=total_entries,
        total_access=total_access,
        max_importance=max_importance,
    )


@memory_app.command("delete")
def delete_cmd(
    memory_id: str = typer.Argument(..., help="Memory entry ID to delete"),
) -> None:
    """Delete a memory entry by ID."""
    c = _get_container()
    entry = _run(c.memory_repo.get_by_id(memory_id))

    if entry is None:
        print_error(f"Memory entry not found: {memory_id}")
        raise typer.Exit(code=1)

    _run(c.memory_repo.delete(memory_id))
    console.print(f"[green]Deleted memory entry {memory_id[:12]}...[/green]")

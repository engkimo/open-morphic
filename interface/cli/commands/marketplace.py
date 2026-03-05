"""Marketplace subcommands — search, install, list, uninstall tools."""

from __future__ import annotations

import typer

from interface.cli.formatters import console, print_error, print_tool_table
from interface.cli.main import _get_container, _run

marketplace_app = typer.Typer()


@marketplace_app.command("search")
def search(
    query: str = typer.Argument(..., help="Search term (tool name or capability)."),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results."),
) -> None:
    """Search the MCP Registry for tools."""
    c = _get_container()
    with console.status("[blue]Searching...[/]"):
        result = _run(c.install_tool.search(query, limit=limit))
    if result.error:
        print_error(f"Registry error: {result.error}")
    print_tool_table(result.candidates)


@marketplace_app.command("install")
def install(
    name: str = typer.Argument(..., help="Tool name to install."),
) -> None:
    """Install a tool from the MCP Registry."""
    c = _get_container()
    with console.status(f"[blue]Installing {name}...[/]"):
        result = _run(c.install_tool.install_by_name(name))
    if result.install_result is None:
        print_error(f"No tool found for '{name}'")
        raise typer.Exit(code=1)
    ir = result.install_result
    if ir.success:
        console.print(f"[green]Installed:[/] {ir.tool_name}")
        if ir.message:
            console.print(f"[dim]{ir.message[:200]}[/]")
    else:
        print_error(ir.error or "Install failed")
        raise typer.Exit(code=1)


@marketplace_app.command("list")
def list_installed() -> None:
    """List all installed tools."""
    c = _get_container()
    tools = c.install_tool.list_installed()
    print_tool_table(tools)


@marketplace_app.command("suggest")
def suggest(
    error: str = typer.Argument(..., help="Error message to analyze."),
    task: str = typer.Option("", "--task", "-t", help="Task description for context."),
) -> None:
    """Suggest tools to fix a task failure."""
    c = _get_container()
    with console.status("[blue]Analyzing failure...[/]"):
        result = _run(c.discover_tools.suggest_for_failure(error, task))
    if result.queries_used:
        console.print(f"[dim]Searched: {', '.join(result.queries_used)}[/]")
    print_tool_table(result.suggestions)


@marketplace_app.command("uninstall")
def uninstall(
    name: str = typer.Argument(..., help="Tool name to uninstall."),
) -> None:
    """Uninstall a previously installed tool."""
    c = _get_container()
    result = _run(c.install_tool.uninstall(name))
    if result.success:
        console.print(f"[green]Uninstalled:[/] {name}")
    else:
        print_error(result.error or "Uninstall failed")
        raise typer.Exit(code=1)

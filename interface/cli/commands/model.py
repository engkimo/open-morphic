"""Model subcommands — list, status, pull, delete, switch, info."""

from __future__ import annotations

import typer

from interface.cli.formatters import (
    console,
    print_error,
    print_model_detail,
    print_model_status,
    print_model_table,
)
from interface.cli.main import _get_container, _run

model_app = typer.Typer()


@model_app.command("list")
def list_models() -> None:
    """List available LLM models."""
    c = _get_container()
    running = _run(c.ollama.is_running())
    if not running:
        console.print("[yellow]Ollama is not running.[/]")
        return
    models = _run(c.ollama.list_models())
    print_model_table(models)


@model_app.command("status")
def status() -> None:
    """Show Ollama status and default model."""
    c = _get_container()
    running = _run(c.ollama.is_running())
    models = _run(c.ollama.list_models()) if running else []
    default_model = c.settings.ollama_default_model
    print_model_status(running, models, default_model)


@model_app.command("pull")
def pull(
    name: str = typer.Argument(..., help="Model name to pull (e.g. qwen3:8b)."),
) -> None:
    """Pull a model from the Ollama registry."""
    c = _get_container()
    with console.status(f"[blue]Pulling {name}...[/]"):
        success = _run(c.ollama.pull_model(name))
    if success:
        console.print(f"[green]Pulled:[/] {name}")
    else:
        print_error(f"Failed to pull {name}")
        raise typer.Exit(code=1)


@model_app.command("delete")
def delete(
    name: str = typer.Argument(..., help="Model name to delete."),
) -> None:
    """Delete a model from local storage."""
    c = _get_container()
    with console.status(f"[blue]Deleting {name}...[/]"):
        success = _run(c.manage_ollama.delete(name))
    if success:
        console.print(f"[green]Deleted:[/] {name}")
    else:
        print_error(f"Failed to delete {name}")
        raise typer.Exit(code=1)


@model_app.command("switch")
def switch(
    name: str = typer.Argument(..., help="Model name to set as default."),
) -> None:
    """Switch the default Ollama model."""
    c = _get_container()
    with console.status(f"[blue]Switching to {name}...[/]"):
        success = _run(c.manage_ollama.switch_default(name))
    if success:
        console.print(f"[green]Default model:[/] {name}")
    else:
        print_error(f"Failed to switch to {name}")
        raise typer.Exit(code=1)


@model_app.command("info")
def info(
    name: str = typer.Argument(..., help="Model name to inspect."),
) -> None:
    """Show detailed info about a model."""
    c = _get_container()
    details = _run(c.manage_ollama.info(name))
    print_model_detail(name, details)

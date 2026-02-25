"""Model subcommands — list, status, pull."""

from __future__ import annotations

import typer

from interface.cli.formatters import console, print_error, print_model_status, print_model_table
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

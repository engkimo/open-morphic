"""morphic serve — one-command HTTP API server startup.

Starts the FastAPI server with auto-detection of available backends.
Falls back gracefully: PostgreSQL → In-Memory.
"""

from __future__ import annotations

import shutil

import typer

from interface.cli.formatters import console

serve_app = typer.Typer()


def _bool_icon(val: bool) -> str:
    return "[green]Yes[/]" if val else "[red]No[/]"


def _print_startup_banner(settings) -> None:  # type: ignore[type-arg]
    """Print a diagnostic summary before starting the server."""
    from rich.panel import Panel
    from rich.table import Table

    # Configuration
    config = Table(show_header=False, box=None, padding=(0, 1))
    config.add_column("Key", style="dim")
    config.add_column("Value")
    config.add_row("Environment", settings.morphic_agent_env.value)
    if settings.use_postgres:
        db_mode = "PostgreSQL"
    elif settings.use_sqlite:
        db_mode = f"SQLite ({settings.sqlite_url})"
    else:
        db_mode = "In-Memory"
    config.add_row("Database", db_mode)
    config.add_row("Local LLM", f"Ollama ({settings.ollama_default_model})")
    config.add_row("Budget", f"${settings.default_monthly_budget_usd:.0f}/month")
    config.add_row("Engine", f"ReAct={'on' if settings.react_enabled else 'off'}")

    console.print(Panel(config, title="Configuration", border_style="blue"))

    # API Keys
    keys = Table(show_header=False, box=None, padding=(0, 1))
    keys.add_column("Provider", style="dim")
    keys.add_column("Status")
    keys.add_row("Anthropic", _bool_icon(settings.has_anthropic))
    keys.add_row("OpenAI", _bool_icon(settings.has_openai))
    keys.add_row("Gemini", _bool_icon(settings.has_gemini))

    console.print(Panel(keys, title="API Keys", border_style="cyan"))

    # CLI tools
    tools = Table(show_header=False, box=None, padding=(0, 1))
    tools.add_column("Tool", style="dim")
    tools.add_column("Status")
    for label, binary in [
        ("claude", settings.claude_code_cli_path),
        ("gemini", settings.gemini_cli_path),
        ("codex", settings.codex_cli_path),
    ]:
        found = shutil.which(binary) is not None
        tools.add_row(label, _bool_icon(found))

    console.print(Panel(tools, title="CLI Tools", border_style="yellow"))

    # Features
    feats = Table(show_header=False, box=None, padding=(0, 1))
    feats.add_column("Feature", style="dim")
    feats.add_column("Status")
    feats.add_row("MCP", _bool_icon(settings.mcp_enabled))
    feats.add_row("Marketplace", _bool_icon(settings.marketplace_enabled))
    feats.add_row("Evolution", _bool_icon(settings.evolution_enabled))
    feats.add_row("LAEE", _bool_icon(settings.laee_enabled))

    console.print(Panel(feats, title="Features", border_style="green"))


@serve_app.command()
def start(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind address."),
    port: int = typer.Option(8001, "--port", "-p", help="Bind port."),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload."),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of workers."),
) -> None:
    """Start the Morphic-Agent HTTP API server."""
    from shared.config import settings

    console.print("[bold]Morphic-Agent v0.5.1[/bold]\n")
    _print_startup_banner(settings)
    console.print(f"\nStarting server on [bold]http://{host}:{port}[/bold]")
    console.print("Press [bold]CTRL+C[/bold] to stop.\n")

    import uvicorn

    uvicorn.run(
        "interface.api.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
        log_level=settings.log_level.lower(),
    )

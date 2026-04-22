"""Context export CLI — cross-platform context bridge for AI tools."""

from __future__ import annotations

from pathlib import Path

import typer

from interface.cli._utils import _get_container, _run
from interface.cli.formatters import (
    console,
    print_error,
    print_export_result,
    print_export_results_table,
)

context_app = typer.Typer()


@context_app.command("export")
def export_cmd(
    platform: str = typer.Argument(
        ...,
        help="Target platform: claude_code, chatgpt, cursor, gemini",
    ),
    query: str = typer.Option("", "--query", "-q", help="Focus query"),
    max_tokens: int = typer.Option(
        None, "--max-tokens", "-t", help="Token budget"
    ),
    output: str = typer.Option(
        None, "--output", "-o", help="Write to file instead of stdout"
    ),
) -> None:
    """Export context for a specific AI platform."""
    c = _get_container()
    bridge = c.context_bridge
    if bridge is None:
        print_error("Context bridge not available")
        raise typer.Exit(code=1)

    try:
        result = _run(
            bridge.export(platform, query=query, max_tokens=max_tokens)
        )
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(code=1) from None

    if output:
        Path(output).write_text(result.content, encoding="utf-8")
        console.print(
            f"[green]Exported to {output}[/] "
            f"(~{result.token_estimate} tokens)"
        )
    else:
        print_export_result(result)


@context_app.command("export-all")
def export_all_cmd(
    query: str = typer.Option("", "--query", "-q", help="Focus query"),
    max_tokens: int = typer.Option(
        None, "--max-tokens", "-t", help="Token budget per platform"
    ),
) -> None:
    """Export context for all supported platforms."""
    c = _get_container()
    bridge = c.context_bridge
    if bridge is None:
        print_error("Context bridge not available")
        raise typer.Exit(code=1)

    results = _run(
        bridge.export_all(query=query, max_tokens=max_tokens)
    )
    print_export_results_table(results)


@context_app.command("platforms")
def platforms_cmd() -> None:
    """List supported export platforms."""
    from infrastructure.memory.context_bridge import SUPPORTED_PLATFORMS

    console.print("[bold]Supported Platforms[/]\n")
    descriptions = {
        "claude_code": "CLAUDE.md-style markdown",
        "chatgpt": "Custom Instructions format",
        "cursor": ".cursorrules numbered rules",
        "gemini": "XML-structured context block",
    }
    for p in SUPPORTED_PLATFORMS:
        desc = descriptions.get(p, "")
        console.print(f"  [cyan]{p}[/]  {desc}")

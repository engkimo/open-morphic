"""Context export CLI — cross-platform context bridge for AI tools."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from application.use_cases.discover_workspace_context import (
    DiscoverWorkspaceContextUseCase,
)
from infrastructure.context.workspace_context_discovery import WorkspaceContextDiscovery
from interface.cli._utils import _get_container, _run
from interface.cli.formatters import (
    console,
    print_error,
    print_export_result,
    print_export_results_table,
)

context_app = typer.Typer()
_SCAN_WORKSPACE_OPTION = typer.Option(
    None,
    "--workspace",
    help="Workspace root.",
)


def _context_scan_payload(index) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "indexed_at": index.indexed_at.isoformat(),
        "source_count": len(index.sources),
        "sources": [
            {
                "content_hash": source.content_hash,
                "precedence": source.precedence,
                "scope": source.scope,
                "sections": source.sections,
                "source_path": source.source_path,
                "source_type": source.source_type.value,
                "warnings": source.warnings,
            }
            for source in index.sources
        ],
        "workspace_root": index.workspace_root,
    }


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


@context_app.command("scan")
def scan_cmd(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    workspace: Path | None = _SCAN_WORKSPACE_OPTION,
) -> None:
    """Scan workspace instruction sources into .morphic/context/index.json."""
    root = workspace or Path.cwd()
    use_case = DiscoverWorkspaceContextUseCase(
        context_discovery=WorkspaceContextDiscovery()
    )
    try:
        result = _run(use_case.execute(workspace_root=str(root)))
    except OSError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    payload = _context_scan_payload(result.index)
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return

    index_path = root / ".morphic" / "context" / "index.json"
    console.print(f"sources={payload['source_count']} index={index_path}")

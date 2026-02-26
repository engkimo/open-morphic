"""CLI commands for MCP server management."""

from __future__ import annotations

import typer

from interface.cli.formatters import console

mcp_app = typer.Typer(no_args_is_help=True)


@mcp_app.command("server")
def mcp_server(
    transport: str = typer.Option("stdio", help="Transport: stdio or streamable-http"),
    port: int = typer.Option(8100, help="Port for HTTP transport"),
) -> None:
    """Launch the Morphic-Agent MCP server."""
    from infrastructure.mcp.server import create_mcp_server
    from interface.api.container import AppContainer

    console.print("[bold]Starting Morphic-Agent MCP Server...[/bold]")

    container = AppContainer()
    mcp = create_mcp_server(container)

    if transport == "streamable-http":
        console.print(f"Transport: streamable-http on port {port}")
        mcp.settings.port = port
        mcp.run(transport="streamable-http")
    else:
        console.print("Transport: stdio")
        mcp.run(transport="stdio")

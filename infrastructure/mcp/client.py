"""MCPClient — connect to external MCP servers, discover tools, adapt to LAEE.

Wraps the official mcp SDK's ClientSession for stdio transport.
MCPToolAdapter converts MCP tools into LAEE-compatible ToolFunc signatures.
discover_and_register() batch-connects to configured servers and registers tools.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from domain.ports.mcp_client import MCPClientPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MCPToolSpec:
    """Description of an MCP tool from a connected server."""

    server_name: str
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class MCPResourceSpec:
    """Description of an MCP resource from a connected server."""

    server_name: str
    uri: str
    name: str
    description: str


@dataclass
class _ServerConnection:
    """Internal record of a connected server."""

    name: str
    command: str
    args: list[str]
    # Actual client/session objects stored here when connected
    client_cm: Any = None  # Context manager for client
    session_cm: Any = None  # Context manager for session
    session: Any = None  # ClientSession
    read_stream: Any = None
    write_stream: Any = None


class MCPClient(MCPClientPort):
    """MCP client implementation using the official mcp SDK.

    Manages multiple server connections via stdio transport.
    """

    def __init__(self) -> None:
        self._connections: dict[str, _ServerConnection] = {}

    @property
    def connected_servers(self) -> list[str]:
        """List names of currently connected servers."""
        return [name for name, conn in self._connections.items() if conn.session is not None]

    async def connect(
        self,
        server_name: str,
        command: str,
        args: list[str] | None = None,
    ) -> None:
        """Connect to an MCP server via stdio transport."""
        if server_name in self._connections and self._connections[server_name].session is not None:
            logger.warning("Server '%s' already connected", server_name)
            return

        try:
            from mcp.client.session import ClientSession
            from mcp.client.stdio import StdioServerParameters, stdio_client

            params = StdioServerParameters(command=command, args=args or [])

            # Enter the stdio_client context manager
            client_cm = stdio_client(params)
            read_stream, write_stream = await client_cm.__aenter__()

            # Enter the ClientSession context manager
            session_cm = ClientSession(read_stream, write_stream)
            session = await session_cm.__aenter__()

            await session.initialize()

            self._connections[server_name] = _ServerConnection(
                name=server_name,
                command=command,
                args=args or [],
                client_cm=client_cm,
                session_cm=session_cm,
                session=session,
                read_stream=read_stream,
                write_stream=write_stream,
            )
            logger.info("Connected to MCP server '%s'", server_name)
        except Exception:
            logger.exception("Failed to connect to MCP server '%s'", server_name)
            raise

    async def disconnect(self, server_name: str) -> None:
        """Disconnect from an MCP server."""
        conn = self._connections.pop(server_name, None)
        if conn is None:
            return
        try:
            if conn.session_cm is not None:
                await conn.session_cm.__aexit__(None, None, None)
            if conn.client_cm is not None:
                await conn.client_cm.__aexit__(None, None, None)
        except Exception:
            logger.warning("Error disconnecting from '%s'", server_name)

    async def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        for name in list(self._connections.keys()):
            await self.disconnect(name)

    async def list_tools(self, server_name: str) -> list[dict[str, Any]]:
        """List available tools from a connected server."""
        conn = self._get_connection(server_name)
        result = await conn.session.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
            }
            for tool in result.tools
        ]

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Call a tool on a connected server."""
        conn = self._get_connection(server_name)
        result = await conn.session.call_tool(tool_name, arguments=arguments or {})
        # Extract text content from the result
        if result.content:
            texts = [c.text for c in result.content if hasattr(c, "text")]
            return "\n".join(texts) if texts else str(result.content)
        return ""

    async def list_resources(self, server_name: str) -> list[dict[str, Any]]:
        """List available resources from a connected server."""
        conn = self._get_connection(server_name)
        result = await conn.session.list_resources()
        return [
            {
                "uri": str(r.uri),
                "name": r.name or "",
                "description": r.description or "",
            }
            for r in result.resources
        ]

    async def read_resource(self, server_name: str, uri: str) -> str:
        """Read a resource from a connected server."""
        from mcp.types import AnyUrl

        conn = self._get_connection(server_name)
        result = await conn.session.read_resource(AnyUrl(uri))
        if result.contents:
            texts = [c.text for c in result.contents if hasattr(c, "text")]
            return "\n".join(texts) if texts else str(result.contents)
        return ""

    def _get_connection(self, server_name: str) -> _ServerConnection:
        """Get a connected server or raise."""
        conn = self._connections.get(server_name)
        if conn is None or conn.session is None:
            msg = f"Server '{server_name}' not connected"
            raise ConnectionError(msg)
        return conn


class MCPToolAdapter:
    """Adapts an MCP tool into a LAEE-compatible callable.

    The adapted function has the signature:
        async def tool_func(**kwargs) -> str
    """

    def __init__(self, client: MCPClient, server_name: str, tool_name: str) -> None:
        self._client = client
        self._server_name = server_name
        self._tool_name = tool_name

    @property
    def name(self) -> str:
        """Prefixed tool name: mcp_{server}_{tool}."""
        return f"mcp_{self._server_name}_{self._tool_name}"

    async def __call__(self, **kwargs: Any) -> str:
        """Call the adapted MCP tool."""
        result = await self._client.call_tool(self._server_name, self._tool_name, kwargs)
        return str(result)


async def discover_and_register(
    client: MCPClient,
    server_configs: list[dict[str, Any]],
) -> list[MCPToolAdapter]:
    """Connect to configured servers and create tool adapters.

    Args:
        client: MCPClient instance.
        server_configs: List of server configs, each with keys:
            - name: Server name
            - command: Server command
            - args: Optional command args

    Returns:
        List of MCPToolAdapter instances for all discovered tools.
    """
    adapters: list[MCPToolAdapter] = []

    for config in server_configs:
        name = config["name"]
        command = config["command"]
        args = config.get("args", [])

        try:
            await client.connect(name, command, args)
            tools = await client.list_tools(name)
            for tool in tools:
                adapter = MCPToolAdapter(client, name, tool["name"])
                adapters.append(adapter)
                logger.info("Registered MCP tool: %s", adapter.name)
        except Exception:
            logger.exception("Failed to discover tools from '%s'", name)

    return adapters

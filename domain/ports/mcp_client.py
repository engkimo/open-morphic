"""MCPClientPort — abstract interface for connecting to external MCP servers.

External boundary port (like LLMGateway). Infrastructure provides the implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MCPClientPort(ABC):
    """Port for connecting to external MCP servers and calling their tools/resources."""

    @abstractmethod
    async def connect(self, server_name: str, command: str, args: list[str] | None = None) -> None:
        """Connect to an MCP server via stdio transport.

        Args:
            server_name: Unique name for this server connection.
            command: Command to launch the server process.
            args: Command-line arguments for the server process.
        """

    @abstractmethod
    async def disconnect(self, server_name: str) -> None:
        """Disconnect from an MCP server.

        Args:
            server_name: Name of the server to disconnect.
        """

    @abstractmethod
    async def list_tools(self, server_name: str) -> list[dict[str, Any]]:
        """List available tools from a connected server.

        Args:
            server_name: Name of the connected server.

        Returns:
            List of tool descriptions (name, description, inputSchema).
        """

    @abstractmethod
    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Call a tool on a connected server.

        Args:
            server_name: Name of the connected server.
            tool_name: Name of the tool to call.
            arguments: Tool arguments.

        Returns:
            Tool result.
        """

    @abstractmethod
    async def list_resources(self, server_name: str) -> list[dict[str, Any]]:
        """List available resources from a connected server.

        Args:
            server_name: Name of the connected server.

        Returns:
            List of resource descriptions (uri, name, description).
        """

    @abstractmethod
    async def read_resource(self, server_name: str, uri: str) -> str:
        """Read a resource from a connected server.

        Args:
            server_name: Name of the connected server.
            uri: Resource URI.

        Returns:
            Resource content as string.
        """

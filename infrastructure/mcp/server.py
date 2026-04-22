"""MorphicMCPServer — expose Morphic-Agent memory as MCP tools and resources.

Separate entry point (not wired into AppContainer directly).
Uses FastMCP from the official Anthropic MCP Python SDK.

6 tools:
  - memory_search: Search L1-L4 hierarchy
  - memory_add: Add content to memory
  - context_compress: Compress history within token budget
  - delta_get_state: Reconstruct current state for topic
  - delta_record: Record state change
  - context_export: Export for specific platform

2 resources:
  - memory://topics: List all delta topics
  - memory://state/{topic}: Current state for a topic
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from interface.api.container import AppContainer

logger = logging.getLogger(__name__)


def create_mcp_server(container: AppContainer) -> FastMCP:
    """Factory: create an MCP server wired to the given AppContainer.

    Args:
        container: AppContainer with memory, context_zipper, delta_encoder, context_bridge.

    Returns:
        Configured FastMCP instance ready to run.
    """
    mcp = FastMCP(
        name="morphic-agent",
        instructions="Morphic-Agent memory and context management tools.",
    )

    # ── Tools ──

    @mcp.tool()
    async def memory_search(query: str, max_tokens: int = 500) -> str:
        """Search Morphic-Agent memory hierarchy (L1-L4).

        Args:
            query: Search query string.
            max_tokens: Maximum tokens for the result.

        Returns:
            Matching memory entries as text.
        """
        if container.memory is None:
            return "Memory not available."
        return await container.memory.retrieve(query, max_tokens=max_tokens)

    @mcp.tool()
    async def memory_add(content: str, role: str = "user") -> str:
        """Add content to Morphic-Agent memory (L1 + L2).

        Args:
            content: Text content to store.
            role: Role label (user, assistant, system).

        Returns:
            Confirmation message.
        """
        if container.memory is None:
            return "Memory not available."
        await container.memory.add(content, role=role)
        return f"Added to memory: {content[:80]}..."

    @mcp.tool()
    async def context_compress(
        query: str,
        history: list[str] | None = None,
        max_tokens: int = 500,
    ) -> str:
        """Compress conversation history within a token budget.

        Args:
            query: Current query for relevance scoring.
            history: List of conversation messages. Defaults to empty.
            max_tokens: Target token budget.

        Returns:
            Compressed context string.
        """
        if container.context_zipper is None:
            return "Context zipper not available."
        return await container.context_zipper.compress(
            history=history or [],
            query=query,
            max_tokens=max_tokens,
        )

    @mcp.tool()
    async def delta_get_state(topic: str) -> str:
        """Reconstruct current state for a delta topic.

        Args:
            topic: Topic name to reconstruct state for.

        Returns:
            JSON-encoded current state.
        """
        if container.delta_encoder is None:
            return "{}"
        state = await container.delta_encoder.get_state(topic)
        return json.dumps(state, ensure_ascii=False, default=str)

    @mcp.tool()
    async def delta_record(topic: str, message: str, changes: str) -> str:
        """Record a state change delta.

        Args:
            topic: Topic name for the state change.
            message: Description of the change.
            changes: JSON-encoded dict of key-value changes.

        Returns:
            Confirmation with delta details.
        """
        if container.delta_encoder is None:
            return "Delta encoder not available."
        parsed_changes: dict[str, Any] = json.loads(changes)
        result = await container.delta_encoder.record(topic, message, parsed_changes)
        return json.dumps(
            {
                "delta_id": result.delta_id,
                "topic": result.topic,
                "seq": result.seq,
                "state_hash": result.state_hash,
            },
            ensure_ascii=False,
        )

    @mcp.tool()
    async def context_export(
        platform: str,
        query: str = "",
        max_tokens: int = 800,
    ) -> str:
        """Export Morphic-Agent context for a specific platform.

        Args:
            platform: Target platform (claude_code, chatgpt, cursor, gemini).
            query: Optional focus query.
            max_tokens: Token budget.

        Returns:
            Formatted context for the target platform.
        """
        if container.context_bridge is None:
            return "Context bridge not available."
        result = await container.context_bridge.export(
            platform=platform,
            query=query,
            max_tokens=max_tokens,
        )
        return result.content

    # ── Resources ──

    @mcp.resource("memory://topics")
    async def list_topics() -> str:
        """List all delta topics in Morphic-Agent memory."""
        if container.delta_encoder is None:
            return "[]"
        topics = await container.delta_encoder.list_topics()
        return json.dumps(topics, ensure_ascii=False)

    @mcp.resource("memory://state/{topic}")
    async def get_topic_state(topic: str) -> str:
        """Get current state for a specific delta topic."""
        if container.delta_encoder is None:
            return "{}"
        state = await container.delta_encoder.get_state(topic)
        return json.dumps(state, ensure_ascii=False, default=str)

    return mcp

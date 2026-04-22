"""ContextBridge — export Morphic-Agent memory in platform-specific formats.

Composes existing MemoryHierarchy + ContextZipper + DeltaEncoderManager to
generate context exports for claude_code, chatgpt, cursor, and gemini platforms.

No new domain port — pure infrastructure. Follows DeltaEncoderManager pattern
with frozen ExportResult dataclass.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from infrastructure.memory.context_zipper import ContextZipper
from infrastructure.memory.delta_encoder import DeltaEncoderManager
from infrastructure.memory.memory_hierarchy import MemoryHierarchy

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = ("claude_code", "chatgpt", "cursor", "gemini")


def _estimate_tokens(text: str) -> int:
    """Approximate token count: ~4 chars per token."""
    return max(1, len(text) // 4)


@dataclass(frozen=True)
class ExportResult:
    """Result returned from export()."""

    platform: str
    content: str
    token_estimate: int


class ContextBridge:
    """Export Morphic-Agent memory/context in platform-specific formats.

    All ports are optional — gracefully degrades when any component is unavailable.
    """

    def __init__(
        self,
        memory: MemoryHierarchy | None = None,
        context_zipper: ContextZipper | None = None,
        delta_encoder: DeltaEncoderManager | None = None,
        default_max_tokens: int = 800,
    ) -> None:
        self._memory = memory
        self._context_zipper = context_zipper
        self._delta_encoder = delta_encoder
        self._default_max_tokens = default_max_tokens

    async def export(
        self,
        platform: str,
        query: str = "",
        max_tokens: int | None = None,
    ) -> ExportResult:
        """Export context for a specific platform.

        Args:
            platform: Target platform (claude_code, chatgpt, cursor, gemini).
            query: Optional search query to focus the export.
            max_tokens: Token budget for the export. Uses default if not specified.

        Returns:
            ExportResult with formatted content.

        Raises:
            ValueError: If platform is not supported.
        """
        if platform not in SUPPORTED_PLATFORMS:
            msg = f"Unsupported platform: {platform}. Supported: {', '.join(SUPPORTED_PLATFORMS)}"
            raise ValueError(msg)

        budget = max_tokens if max_tokens is not None else self._default_max_tokens
        raw_context = await self._gather_context(query, budget)

        formatters = {
            "claude_code": self._format_claude_code,
            "chatgpt": self._format_chatgpt,
            "cursor": self._format_cursor,
            "gemini": self._format_gemini,
        }

        content = formatters[platform](raw_context, query)

        return ExportResult(
            platform=platform,
            content=content,
            token_estimate=_estimate_tokens(content),
        )

    async def export_all(
        self,
        query: str = "",
        max_tokens: int | None = None,
    ) -> list[ExportResult]:
        """Export context for all supported platforms.

        Returns a list of ExportResult, one per platform.
        """
        results: list[ExportResult] = []
        for platform in SUPPORTED_PLATFORMS:
            result = await self.export(platform, query=query, max_tokens=max_tokens)
            results.append(result)
        return results

    async def _gather_context(self, query: str, max_tokens: int) -> dict[str, Any]:
        """Gather raw context from all available sources."""
        context: dict[str, Any] = {
            "memory": "",
            "compressed": "",
            "state": {},
            "topics": [],
        }

        # Memory retrieval
        if self._memory is not None and query:
            try:
                context["memory"] = await self._memory.retrieve(query, max_tokens=max_tokens)
            except Exception:
                logger.warning("Memory retrieval failed during context export")

        # Context compression
        if self._context_zipper is not None and query:
            try:
                context["compressed"] = await self._context_zipper.compress(
                    history=[],
                    query=query,
                    max_tokens=max_tokens,
                )
            except Exception:
                logger.warning("Context compression failed during context export")

        # Delta state
        if self._delta_encoder is not None:
            try:
                topics = await self._delta_encoder.list_topics()
                context["topics"] = topics
                if topics:
                    states: dict[str, dict] = {}
                    for topic in topics[:5]:  # Limit to 5 topics
                        states[topic] = await self._delta_encoder.get_state(topic)
                    context["state"] = states
            except Exception:
                logger.warning("Delta state retrieval failed during context export")

        return context

    def _format_claude_code(self, context: dict[str, Any], query: str) -> str:
        """Format as CLAUDE.md-style markdown."""
        sections: list[str] = ["# Morphic-Agent Context"]

        if query:
            sections.append(f"\n## Query\n{query}")

        state = context.get("state", {})
        if state:
            sections.append("\n## Current State")
            for topic, data in state.items():
                sections.append(f"\n### {topic}")
                for key, value in data.items():
                    sections.append(f"- **{key}**: {value}")

        memory = context.get("memory", "")
        if memory:
            sections.append(f"\n## Recent Memory\n{memory}")

        compressed = context.get("compressed", "")
        if compressed:
            sections.append(f"\n## Context\n{compressed}")

        return "\n".join(sections)

    def _format_chatgpt(self, context: dict[str, Any], query: str) -> str:
        """Format as ChatGPT Custom Instructions."""
        know_parts: list[str] = []
        respond_parts: list[str] = []

        # "What would you like ChatGPT to know?"
        state = context.get("state", {})
        if state:
            know_parts.append("Project State:")
            for topic, data in state.items():
                items = ", ".join(f"{k}={v}" for k, v in data.items())
                know_parts.append(f"- {topic}: {items}")

        memory = context.get("memory", "")
        if memory:
            know_parts.append(f"\nRelevant Context:\n{memory}")

        # "How should ChatGPT respond?"
        respond_parts.append("Use the project state and context above when answering.")
        if query:
            respond_parts.append(f"Focus on: {query}")

        know_section = "\n".join(know_parts) if know_parts else "No project context available."
        respond_section = "\n".join(respond_parts)

        return (
            f"## What would you like ChatGPT to know?\n{know_section}\n\n"
            f"## How should ChatGPT respond?\n{respond_section}"
        )

    def _format_cursor(self, context: dict[str, Any], query: str) -> str:
        """Format as .cursorrules-style numbered rules."""
        rules: list[str] = []
        rule_num = 1

        state = context.get("state", {})
        if state:
            for topic, data in state.items():
                items = ", ".join(f"{k}={v}" for k, v in data.items())
                rules.append(f"{rule_num}. Project '{topic}': {items}")
                rule_num += 1

        memory = context.get("memory", "")
        if memory:
            for line in memory.split("\n"):
                line = line.strip()
                if line and line != "---":
                    rules.append(f"{rule_num}. {line}")
                    rule_num += 1

        if query:
            rules.append(f"{rule_num}. Current focus: {query}")
            rule_num += 1

        if not rules:
            return "# Morphic-Agent Context\nNo context available."

        return "# Morphic-Agent Context\n" + "\n".join(rules)

    def _format_gemini(self, context: dict[str, Any], query: str) -> str:
        """Format as Gemini system instruction with structured context block."""
        blocks: list[str] = ["<morphic-context>"]

        state = context.get("state", {})
        if state:
            blocks.append("<state>")
            for topic, data in state.items():
                items = ", ".join(f"{k}: {v}" for k, v in data.items())
                blocks.append(f"  {topic} = {{ {items} }}")
            blocks.append("</state>")

        memory = context.get("memory", "")
        if memory:
            blocks.append(f"<memory>\n{memory}\n</memory>")

        if query:
            blocks.append(f"<focus>{query}</focus>")

        blocks.append("</morphic-context>")

        return "\n".join(blocks)

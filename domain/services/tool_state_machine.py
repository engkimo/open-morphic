"""ToolStateMachine — Manus Principle 2: mask tools, never remove them.

Pure domain service. Controls tool availability without changing the tool
definition set, preserving KV-cache stability.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.value_objects.tool_state import ToolState


@dataclass(frozen=True)
class ToolDefinition:
    """Immutable tool definition with name, description, and parameter schema."""

    name: str
    description: str = ""
    parameters: dict = field(default_factory=dict)


class ToolStateMachine:
    """Manage tool visibility via masking. Tool count is invariant.

    Invariant: len(get_all_tools()) is constant after initialization.
    Tools are never added or removed — only masked/unmasked.
    """

    def __init__(self, tools: list[ToolDefinition]) -> None:
        self._tools: dict[str, ToolDefinition] = {t.name: t for t in tools}
        self._states: dict[str, ToolState] = {t.name: ToolState.ENABLED for t in tools}
        self._total_count = len(tools)

    @property
    def total_count(self) -> int:
        """Total tool count — invariant, never changes."""
        return self._total_count

    def get_state(self, tool_name: str) -> ToolState:
        """Return current state for a tool. Raises KeyError if unknown."""
        return self._states[tool_name]

    def mask(self, tool_name: str) -> None:
        """Mask a tool (disable without removing). Raises KeyError if unknown."""
        if tool_name not in self._states:
            raise KeyError(f"Unknown tool: {tool_name}")
        self._states[tool_name] = ToolState.MASKED

    def unmask(self, tool_name: str) -> None:
        """Unmask a tool (re-enable). Raises KeyError if unknown."""
        if tool_name not in self._states:
            raise KeyError(f"Unknown tool: {tool_name}")
        self._states[tool_name] = ToolState.ENABLED

    def get_enabled_tools(self) -> list[ToolDefinition]:
        """Return only tools in ENABLED state."""
        return [
            self._tools[name] for name, state in self._states.items() if state == ToolState.ENABLED
        ]

    def get_all_tools(self) -> list[ToolDefinition]:
        """Return all tools regardless of state. Count is invariant."""
        return list(self._tools.values())

    def mask_by_prefix(self, prefix: str) -> int:
        """Mask all tools whose name starts with prefix. Return count masked."""
        count = 0
        for name in self._states:
            if name.startswith(prefix) and self._states[name] == ToolState.ENABLED:
                self._states[name] = ToolState.MASKED
                count += 1
        return count

    def unmask_by_prefix(self, prefix: str) -> int:
        """Unmask all tools whose name starts with prefix. Return count unmasked."""
        count = 0
        for name in self._states:
            if name.startswith(prefix) and self._states[name] == ToolState.MASKED:
                self._states[name] = ToolState.ENABLED
                count += 1
        return count

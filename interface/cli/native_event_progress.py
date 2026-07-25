"""Concise terminal rendering for normalized native-engine events."""

from __future__ import annotations

from collections.abc import Callable

from domain.entities.agent_engine_event import AgentEngineEvent, AgentEngineEventType
from domain.ports.agent_engine import AgentEngineEventSinkPort
from interface.cli.formatters import console

_LABELS = {
    AgentEngineEventType.RUN_STARTED: "started",
    AgentEngineEventType.TOOL_STARTED: "tool started",
    AgentEngineEventType.TOOL_COMPLETED: "tool completed",
    AgentEngineEventType.FILE_CHANGED: "file changed",
    AgentEngineEventType.PLAN_UPDATED: "plan updated",
    AgentEngineEventType.RUN_COMPLETED: "completed",
    AgentEngineEventType.RUN_FAILED: "failed",
    AgentEngineEventType.ERROR: "error",
}
_DETAIL_TYPES = {
    AgentEngineEventType.TOOL_STARTED,
    AgentEngineEventType.TOOL_COMPLETED,
    AgentEngineEventType.FILE_CHANGED,
    AgentEngineEventType.PLAN_UPDATED,
    AgentEngineEventType.RUN_FAILED,
    AgentEngineEventType.ERROR,
}


class NativeEventProgressRenderer(AgentEngineEventSinkPort):
    """Render selected lifecycle events without exposing raw provider payloads."""

    def __init__(self, printer: Callable[[str], None] | None = None) -> None:
        self._printer = printer or console.print

    async def publish(self, event: AgentEngineEvent) -> None:
        label = _LABELS.get(event.type)
        if label is None:
            return
        line = f"{event.engine.value} | {label}"
        if event.type in _DETAIL_TYPES and event.text:
            line = f"{line}: {self._compact(event.text)}"
        self._printer(line)

    def _compact(self, value: str, limit: int = 160) -> str:
        text = " ".join(value.split())
        if len(text) <= limit:
            return text
        return f"{text[: limit - 1]}…"

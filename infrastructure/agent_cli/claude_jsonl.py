"""Normalize Claude Code stream-json output into Morphic events."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from domain.entities.agent_engine_event import AgentEngineEvent, AgentEngineEventType
from domain.value_objects.agent_engine import AgentEngineType


@dataclass(frozen=True)
class ClaudeParsedRun:
    output: str
    events: list[AgentEngineEvent] = field(default_factory=list)
    session_id: str | None = None
    model: str | None = None
    usage: dict[str, int] | None = None
    cost_usd: float = 0.0
    error: str | None = None
    parse_errors: int = 0


class ClaudeJsonlEventDecoder:
    def __init__(self) -> None:
        self._sequence = 0
        self.session_id: str | None = None

    def decode(self, line: str) -> list[AgentEngineEvent]:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            return []
        if not isinstance(raw, dict) or "type" not in raw:
            return []
        session_id = raw.get("session_id")
        if isinstance(session_id, str) and session_id:
            self.session_id = session_id
        return self._events(raw)

    def _events(self, raw: dict[str, Any]) -> list[AgentEngineEvent]:
        raw_type = raw.get("type")
        if raw_type == "system" and raw.get("subtype") == "init":
            return [self._event(AgentEngineEventType.RUN_STARTED, raw)]
        if raw_type == "result":
            event_type = (
                AgentEngineEventType.RUN_FAILED
                if raw.get("is_error") or raw.get("subtype") != "success"
                else AgentEngineEventType.RUN_COMPLETED
            )
            return [self._event(event_type, raw, text=_string(raw.get("result")))]
        message = raw.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            return []
        events: list[AgentEngineEvent] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if raw_type == "assistant" and block_type == "tool_use":
                events.append(
                    self._event(
                        AgentEngineEventType.TOOL_STARTED,
                        raw,
                        item_id=_string(block.get("id")),
                        item_type=_string(block.get("name")),
                        text=_tool_text(block),
                    )
                )
            elif raw_type == "user" and block_type == "tool_result":
                events.append(
                    self._event(
                        AgentEngineEventType.TOOL_COMPLETED,
                        raw,
                        item_id=_string(block.get("tool_use_id")),
                        item_type="tool_result",
                        text=_string(block.get("content")),
                    )
                )
            elif raw_type == "assistant" and block_type == "text":
                events.append(
                    self._event(
                        AgentEngineEventType.ASSISTANT_MESSAGE,
                        raw,
                        text=_string(block.get("text")),
                    )
                )
        return events

    def _event(
        self,
        event_type: AgentEngineEventType,
        raw: dict[str, Any],
        *,
        item_id: str | None = None,
        item_type: str | None = None,
        text: str | None = None,
    ) -> AgentEngineEvent:
        event = AgentEngineEvent(
            type=event_type,
            engine=AgentEngineType.CLAUDE_CODE,
            sequence=self._sequence,
            session_id=self.session_id,
            item_id=item_id,
            item_type=item_type,
            text=text,
            payload=raw,
        )
        self._sequence += 1
        return event


def parse_claude_output(stdout: str) -> ClaudeParsedRun:
    decoder = ClaudeJsonlEventDecoder()
    events: list[AgentEngineEvent] = []
    decoded: list[dict[str, Any]] = []
    parse_errors = 0
    for line in stdout.splitlines():
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            parse_errors += 1
            continue
        if isinstance(raw, dict):
            decoded.append(raw)
        events.extend(decoder.decode(line))
    result = next((item for item in reversed(decoded) if item.get("type") == "result"), {})
    init = next((item for item in decoded if item.get("type") == "system"), {})
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else None
    error = None
    if result and (result.get("is_error") or result.get("subtype") != "success"):
        error = str(result.get("result") or result.get("subtype") or "Claude run failed")
    return ClaudeParsedRun(
        output=str(result.get("result") or stdout),
        events=events,
        session_id=decoder.session_id,
        model=_string(init.get("model")),
        usage=usage,
        cost_usd=float(result.get("total_cost_usd") or 0.0),
        error=error,
        parse_errors=parse_errors,
    )


def _tool_text(block: dict[str, Any]) -> str | None:
    tool_input = block.get("input")
    if isinstance(tool_input, dict):
        for key in ("command", "file_path", "path"):
            value = _string(tool_input.get(key))
            if value:
                return value
    return _string(block.get("name"))


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None

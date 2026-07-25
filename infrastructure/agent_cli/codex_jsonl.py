"""Parse Codex CLI JSONL into Morphic native-engine events."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from domain.entities.agent_engine_event import AgentEngineEvent, AgentEngineEventType
from domain.value_objects.agent_engine import AgentEngineType


@dataclass(frozen=True)
class CodexParsedRun:
    output: str
    events: list[AgentEngineEvent] = field(default_factory=list)
    session_id: str | None = None
    usage: dict[str, int] | None = None
    model: str | None = None
    error: str | None = None
    parse_errors: int = 0


class CodexJsonlEventDecoder:
    """Stateful decoder for incremental Codex JSONL event delivery."""

    def __init__(self) -> None:
        self._sequence = 0
        self._session_id: str | None = None

    def decode(self, line: str) -> AgentEngineEvent | None:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(raw, dict) or "type" not in raw:
            return None
        if raw.get("type") == "thread.started":
            self._session_id = _optional_string(raw.get("thread_id"))
        event = _normalize_event(
            raw,
            sequence=self._sequence,
            session_id=self._session_id,
        )
        self._sequence += 1
        return event


def parse_codex_output(stdout: str) -> CodexParsedRun:
    """Parse current JSONL output while preserving legacy single-JSON compatibility."""

    stripped = stdout.strip()
    if not stripped:
        return CodexParsedRun(output="")

    lines = [line for line in stripped.splitlines() if line.strip()]
    decoded: list[dict[str, Any]] = []
    parse_errors = 0
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            parse_errors += 1
            continue
        if isinstance(value, dict):
            decoded.append(value)
        else:
            parse_errors += 1

    if len(decoded) == 1 and "type" not in decoded[0]:
        legacy = decoded[0]
        return CodexParsedRun(
            output=str(legacy.get("result", stdout)),
            usage=_usage_dict(legacy.get("usage")),
            model=_optional_string(legacy.get("model")),
            parse_errors=parse_errors,
        )
    if not decoded:
        return CodexParsedRun(output=stdout, parse_errors=parse_errors)

    events: list[AgentEngineEvent] = []
    session_id: str | None = None
    final_message: str | None = None
    usage: dict[str, int] | None = None
    error: str | None = None
    for raw in decoded:
        raw_type = str(raw.get("type", ""))
        if raw_type == "thread.started":
            session_id = _optional_string(raw.get("thread_id"))
        if raw_type == "turn.completed":
            usage = _usage_dict(raw.get("usage"))
        if raw_type in {"turn.failed", "error"}:
            error = _error_text(raw)

        item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
        if item.get("type") == "agent_message" and raw_type == "item.completed":
            final_message = _optional_string(item.get("text")) or final_message

        events.append(
            _normalize_event(raw, sequence=len(events), session_id=session_id)
        )

    return CodexParsedRun(
        output=final_message or stdout,
        events=events,
        session_id=session_id,
        usage=usage,
        error=error,
        parse_errors=parse_errors,
    )


def _normalize_event(
    raw: dict[str, Any],
    *,
    sequence: int,
    session_id: str | None,
) -> AgentEngineEvent:
    raw_type = str(raw.get("type", ""))
    item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
    item_type = _optional_string(item.get("type"))
    return AgentEngineEvent(
        type=_event_type(raw_type, item_type),
        engine=AgentEngineType.CODEX_CLI,
        sequence=sequence,
        session_id=session_id,
        item_id=_optional_string(item.get("id")),
        item_type=item_type,
        text=_event_text(item, raw),
        payload=raw,
    )


def _event_type(raw_type: str, item_type: str | None) -> AgentEngineEventType:
    if raw_type == "thread.started":
        return AgentEngineEventType.RUN_STARTED
    if raw_type == "turn.started":
        return AgentEngineEventType.TURN_STARTED
    if raw_type == "turn.completed":
        return AgentEngineEventType.RUN_COMPLETED
    if raw_type == "turn.failed":
        return AgentEngineEventType.RUN_FAILED
    if raw_type == "error":
        return AgentEngineEventType.ERROR
    if raw_type in {"item.started", "item.completed"}:
        if item_type == "agent_message":
            return AgentEngineEventType.ASSISTANT_MESSAGE
        if item_type == "file_change":
            return AgentEngineEventType.FILE_CHANGED
        if item_type in {"plan_update", "todo_list"}:
            return AgentEngineEventType.PLAN_UPDATED
        if item_type in {"command_execution", "mcp_tool_call", "web_search"}:
            return (
                AgentEngineEventType.TOOL_STARTED
                if raw_type == "item.started"
                else AgentEngineEventType.TOOL_COMPLETED
            )
        return AgentEngineEventType.PROGRESS
    return AgentEngineEventType.UNKNOWN


def _event_text(item: dict[str, Any], raw: dict[str, Any]) -> str | None:
    for value in [
        item.get("text"),
        item.get("command"),
        item.get("name"),
        raw.get("message"),
        raw.get("error"),
    ]:
        text = _optional_string(value)
        if text:
            return text
    return None


def _error_text(raw: dict[str, Any]) -> str:
    error = raw.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(error or raw.get("message") or "Codex turn failed")


def _usage_dict(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    return {
        str(key): int(token_count)
        for key, token_count in value.items()
        if isinstance(token_count, int) and not isinstance(token_count, bool)
    }


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None

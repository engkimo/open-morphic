"""Shared helpers for context adapters."""

from __future__ import annotations

import re

from domain.entities.cognitive import SharedTaskState


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


def _truncate_to_budget(text: str, max_tokens: int) -> str:
    """Truncate text to approximate token budget."""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... [truncated]"


def _format_decisions(state: SharedTaskState, limit: int = 10) -> str:
    """Format recent decisions as bullet list."""
    if not state.decisions:
        return ""
    lines = ["## Decisions"]
    for d in state.decisions[-limit:]:
        lines.append(f"- [{d.agent_engine.value}] {d.description} (confidence: {d.confidence})")
        if d.rationale:
            lines.append(f"  Rationale: {d.rationale}")
    return "\n".join(lines)


def _format_artifacts(state: SharedTaskState) -> str:
    """Format artifacts as key-value list."""
    if not state.artifacts:
        return ""
    lines = ["## Artifacts"]
    for key, value in state.artifacts.items():
        lines.append(f"- **{key}**: {value}")
    return "\n".join(lines)


def _format_blockers(state: SharedTaskState) -> str:
    """Format blockers as bullet list."""
    if not state.blockers:
        return ""
    lines = ["## Blockers"]
    for b in state.blockers:
        lines.append(f"- {b}")
    return "\n".join(lines)


def _format_history(state: SharedTaskState, limit: int = 5) -> str:
    """Format recent agent history."""
    if not state.agent_history:
        return ""
    lines = ["## Agent History"]
    for a in state.agent_history[-limit:]:
        lines.append(f"- [{a.agent_engine.value}] {a.action_type}: {a.summary}")
    return "\n".join(lines)


# Regex patterns for insight extraction
_DECISION_PATTERN = re.compile(
    r"(?:decided|chose|selected|picked|went with|using)\s+(.+?)(?:\.|$)",
    re.IGNORECASE,
)
_ERROR_PATTERN = re.compile(
    r"(?:error|failed|exception|traceback|bug|issue)[:.]?\s*(.+?)(?:\.|$)",
    re.IGNORECASE,
)
_FILE_PATTERN = re.compile(
    r"(?:created?|modified?|updated?|wrote|generated)\s+(?:file\s+)?[`'\"]?(\S+\.\w+)[`'\"]?",
    re.IGNORECASE,
)
_FACT_PATTERN = re.compile(
    r"(?:uses?|requires?|depends on|built with|configured with)\s+(.+?)(?:\.|$)",
    re.IGNORECASE,
)

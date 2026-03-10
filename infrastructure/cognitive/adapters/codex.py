"""CodexContextAdapter — AGENTS.md format injection, code output extraction."""

from __future__ import annotations

from domain.entities.cognitive import SharedTaskState
from domain.ports.context_adapter import AdapterInsight, ContextAdapterPort
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.cognitive import CognitiveMemoryType
from infrastructure.cognitive.adapters._base import (
    _DECISION_PATTERN,
    _ERROR_PATTERN,
    _FILE_PATTERN,
    _format_artifacts,
    _format_blockers,
    _format_decisions,
    _truncate_to_budget,
)


class CodexContextAdapter(ContextAdapterPort):
    """OpenAI Codex CLI: AGENTS.md format. Code-centric extraction."""

    def engine_type(self) -> AgentEngineType:
        return AgentEngineType.CODEX_CLI

    def inject_context(
        self,
        state: SharedTaskState,
        memory_context: str,
        max_tokens: int = 2000,
    ) -> str:
        # Codex uses AGENTS.md-style flat markdown
        sections: list[str] = [
            "# AGENTS.md — Morphic-Agent Context",
            f"\n## Task\n{state.task_id}",
        ]

        decisions = _format_decisions(state, limit=5)
        if decisions:
            sections.append(decisions)

        artifacts = _format_artifacts(state)
        if artifacts:
            sections.append(artifacts)

        blockers = _format_blockers(state)
        if blockers:
            sections.append(blockers)

        if memory_context:
            sections.append(f"## Context\n{memory_context}")

        result = "\n\n".join(sections)
        return _truncate_to_budget(result, max_tokens)

    def extract_insights(self, output: str) -> list[AdapterInsight]:
        insights: list[AdapterInsight] = []

        # Codex is code-centric — file artifacts are high confidence
        for match in _FILE_PATTERN.finditer(output):
            insights.append(
                AdapterInsight(
                    content=f"File: {match.group(1).strip()}",
                    memory_type=CognitiveMemoryType.EPISODIC,
                    confidence=0.9,
                    tags=["artifact", "file", "code"],
                )
            )

        for match in _DECISION_PATTERN.finditer(output):
            insights.append(
                AdapterInsight(
                    content=match.group(1).strip(),
                    memory_type=CognitiveMemoryType.EPISODIC,
                    confidence=0.6,
                    tags=["decision"],
                )
            )

        for match in _ERROR_PATTERN.finditer(output):
            insights.append(
                AdapterInsight(
                    content=match.group(1).strip(),
                    memory_type=CognitiveMemoryType.PROCEDURAL,
                    confidence=0.7,
                    tags=["error", "code"],
                )
            )

        return insights

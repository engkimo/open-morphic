"""ClaudeCodeContextAdapter — CLAUDE.md format injection, decision/artifact extraction."""

from __future__ import annotations

from domain.entities.cognitive import SharedTaskState
from domain.ports.context_adapter import AdapterInsight, ContextAdapterPort
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.cognitive import CognitiveMemoryType
from infrastructure.cognitive.adapters._base import (
    _DECISION_PATTERN,
    _ERROR_PATTERN,
    _FACT_PATTERN,
    _FILE_PATTERN,
    _format_artifacts,
    _format_blockers,
    _format_decisions,
    _format_history,
    _truncate_to_budget,
)


class ClaudeCodeContextAdapter(ContextAdapterPort):
    """Claude Code SDK: CLAUDE.md format. 200K context window."""

    def engine_type(self) -> AgentEngineType:
        return AgentEngineType.CLAUDE_CODE

    def inject_context(
        self,
        state: SharedTaskState,
        memory_context: str,
        max_tokens: int = 2000,
    ) -> str:
        sections: list[str] = [f"# Morphic-Agent Shared Context\n\n## Task: {state.task_id}"]

        decisions = _format_decisions(state)
        if decisions:
            sections.append(decisions)

        artifacts = _format_artifacts(state)
        if artifacts:
            sections.append(artifacts)

        blockers = _format_blockers(state)
        if blockers:
            sections.append(blockers)

        history = _format_history(state)
        if history:
            sections.append(history)

        if memory_context:
            sections.append(f"## Memory\n{memory_context}")

        result = "\n\n".join(sections)
        return _truncate_to_budget(result, max_tokens)

    def extract_insights(self, output: str) -> list[AdapterInsight]:
        insights: list[AdapterInsight] = []

        for match in _DECISION_PATTERN.finditer(output):
            insights.append(
                AdapterInsight(
                    content=match.group(1).strip(),
                    memory_type=CognitiveMemoryType.EPISODIC,
                    confidence=0.7,
                    tags=["decision"],
                )
            )

        for match in _FILE_PATTERN.finditer(output):
            insights.append(
                AdapterInsight(
                    content=f"File: {match.group(1).strip()}",
                    memory_type=CognitiveMemoryType.EPISODIC,
                    confidence=0.8,
                    tags=["artifact", "file"],
                )
            )

        for match in _ERROR_PATTERN.finditer(output):
            insights.append(
                AdapterInsight(
                    content=match.group(1).strip(),
                    memory_type=CognitiveMemoryType.PROCEDURAL,
                    confidence=0.6,
                    tags=["error"],
                )
            )

        for match in _FACT_PATTERN.finditer(output):
            insights.append(
                AdapterInsight(
                    content=match.group(1).strip(),
                    memory_type=CognitiveMemoryType.SEMANTIC,
                    confidence=0.6,
                    tags=["fact"],
                )
            )

        return insights

"""GeminiContextAdapter — full context dump (2M window), research insight extraction."""

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


class GeminiContextAdapter(ContextAdapterPort):
    """Gemini CLI + ADK: XML-tagged full context. 2M token window allows verbose injection."""

    def engine_type(self) -> AgentEngineType:
        return AgentEngineType.GEMINI_CLI

    def inject_context(
        self,
        state: SharedTaskState,
        memory_context: str,
        max_tokens: int = 2000,
    ) -> str:
        # Gemini has 2M window — use XML blocks for structured context
        blocks: list[str] = ["<morphic-context>"]
        blocks.append(f"<task-id>{state.task_id}</task-id>")

        decisions = _format_decisions(state, limit=20)
        if decisions:
            blocks.append(f"<decisions>\n{decisions}\n</decisions>")

        artifacts = _format_artifacts(state)
        if artifacts:
            blocks.append(f"<artifacts>\n{artifacts}\n</artifacts>")

        blockers = _format_blockers(state)
        if blockers:
            blocks.append(f"<blockers>\n{blockers}\n</blockers>")

        history = _format_history(state, limit=10)
        if history:
            blocks.append(f"<agent-history>\n{history}\n</agent-history>")

        if memory_context:
            blocks.append(f"<memory>\n{memory_context}\n</memory>")

        blocks.append("</morphic-context>")
        result = "\n".join(blocks)
        return _truncate_to_budget(result, max_tokens)

    def extract_insights(self, output: str) -> list[AdapterInsight]:
        insights: list[AdapterInsight] = []

        # Gemini excels at research — extract semantic facts with higher confidence
        for match in _FACT_PATTERN.finditer(output):
            insights.append(
                AdapterInsight(
                    content=match.group(1).strip(),
                    memory_type=CognitiveMemoryType.SEMANTIC,
                    confidence=0.7,
                    tags=["fact", "research"],
                )
            )

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

        return insights

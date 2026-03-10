"""ADKContextAdapter — workflow state injection, pipeline output extraction."""

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


class ADKContextAdapter(ContextAdapterPort):
    """Google ADK: workflow-style context. Sequential/Parallel/Loop agents."""

    def engine_type(self) -> AgentEngineType:
        return AgentEngineType.ADK

    def inject_context(
        self,
        state: SharedTaskState,
        memory_context: str,
        max_tokens: int = 2000,
    ) -> str:
        # ADK uses structured workflow state
        sections: list[str] = [f"<workflow-context task='{state.task_id}'>"]

        decisions = _format_decisions(state, limit=10)
        if decisions:
            sections.append(decisions)

        artifacts = _format_artifacts(state)
        if artifacts:
            sections.append(artifacts)

        blockers = _format_blockers(state)
        if blockers:
            sections.append(blockers)

        history = _format_history(state, limit=10)
        if history:
            sections.append(history)

        if memory_context:
            sections.append(f"## Pipeline Memory\n{memory_context}")

        sections.append("</workflow-context>")
        result = "\n\n".join(sections)
        return _truncate_to_budget(result, max_tokens)

    def extract_insights(self, output: str) -> list[AdapterInsight]:
        insights: list[AdapterInsight] = []

        # ADK produces pipeline outputs — structured facts and decisions
        for match in _FACT_PATTERN.finditer(output):
            insights.append(
                AdapterInsight(
                    content=match.group(1).strip(),
                    memory_type=CognitiveMemoryType.SEMANTIC,
                    confidence=0.7,
                    tags=["fact", "pipeline"],
                )
            )

        for match in _DECISION_PATTERN.finditer(output):
            insights.append(
                AdapterInsight(
                    content=match.group(1).strip(),
                    memory_type=CognitiveMemoryType.EPISODIC,
                    confidence=0.7,
                    tags=["decision", "pipeline"],
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
                    tags=["error", "pipeline"],
                )
            )

        return insights

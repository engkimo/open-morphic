"""OllamaContextAdapter — heavily compressed injection, basic extraction."""

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
    _truncate_to_budget,
)


class OllamaContextAdapter(ContextAdapterPort):
    """Ollama local: heavily compressed context. Small window demands brevity."""

    def engine_type(self) -> AgentEngineType:
        return AgentEngineType.OLLAMA

    def inject_context(
        self,
        state: SharedTaskState,
        memory_context: str,
        max_tokens: int = 2000,
    ) -> str:
        # Ollama has limited context — ultra-compact format
        parts: list[str] = [f"Task: {state.task_id}"]

        if state.decisions:
            recent = state.decisions[-3:]
            parts.append("Decisions: " + "; ".join(d.description for d in recent))

        if state.blockers:
            parts.append("Blockers: " + "; ".join(state.blockers[:3]))

        if state.artifacts:
            items = list(state.artifacts.items())[:5]
            parts.append("Artifacts: " + ", ".join(f"{k}={v}" for k, v in items))

        if memory_context:
            parts.append(f"Memory: {memory_context}")

        result = "\n".join(parts)
        return _truncate_to_budget(result, max_tokens)

    def extract_insights(self, output: str) -> list[AdapterInsight]:
        insights: list[AdapterInsight] = []

        for match in _DECISION_PATTERN.finditer(output):
            insights.append(
                AdapterInsight(
                    content=match.group(1).strip(),
                    memory_type=CognitiveMemoryType.EPISODIC,
                    confidence=0.5,
                    tags=["decision"],
                )
            )

        for match in _FILE_PATTERN.finditer(output):
            insights.append(
                AdapterInsight(
                    content=f"File: {match.group(1).strip()}",
                    memory_type=CognitiveMemoryType.EPISODIC,
                    confidence=0.6,
                    tags=["artifact", "file"],
                )
            )

        for match in _ERROR_PATTERN.finditer(output):
            insights.append(
                AdapterInsight(
                    content=match.group(1).strip(),
                    memory_type=CognitiveMemoryType.PROCEDURAL,
                    confidence=0.5,
                    tags=["error"],
                )
            )

        for match in _FACT_PATTERN.finditer(output):
            insights.append(
                AdapterInsight(
                    content=match.group(1).strip(),
                    memory_type=CognitiveMemoryType.SEMANTIC,
                    confidence=0.4,
                    tags=["fact"],
                )
            )

        return insights

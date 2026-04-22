"""SubtaskTypeClassifier — infer TaskType from subtask description.

Combines TopicExtractor + TaskComplexityClassifier to determine which
AgentEngineType should handle a subtask. Pure domain service, no I/O.
"""

from __future__ import annotations

from domain.services.task_complexity import TaskComplexityClassifier
from domain.services.topic_extractor import TopicExtractor
from domain.value_objects.model_tier import TaskType
from domain.value_objects.task_complexity import TaskComplexity

# Topic → TaskType mapping (aligned with CLAUDE.md AGENT_ROUTING_MAP)
_TOPIC_TO_TASK_TYPE: dict[str, TaskType] = {
    "backend": TaskType.CODE_GENERATION,
    "frontend": TaskType.CODE_GENERATION,
    "database": TaskType.CODE_GENERATION,
    "testing": TaskType.CODE_GENERATION,
    "ml": TaskType.COMPLEX_REASONING,
    "security": TaskType.COMPLEX_REASONING,
    "refactoring": TaskType.COMPLEX_REASONING,
    "data": TaskType.LONG_CONTEXT,
    "documentation": TaskType.FILE_OPERATION,
    "devops": TaskType.FILE_OPERATION,
}


class SubtaskTypeClassifier:
    """Classify a subtask description into a TaskType for engine routing."""

    @staticmethod
    def infer(description: str) -> TaskType:
        """Infer TaskType from subtask description text.

        Priority:
          1. requires_tools → WEB_SEARCH (needs Grounding-capable engine)
          2. complexity == COMPLEX → COMPLEX_REASONING
          3. topic-based mapping
          4. fallback → SIMPLE_QA
        """
        if not description or not description.strip():
            return TaskType.SIMPLE_QA

        # Web/real-time tasks need Grounding-capable engine (Gemini CLI)
        if TaskComplexityClassifier.requires_tools(description):
            return TaskType.WEB_SEARCH

        # Complex tasks benefit from stronger reasoning
        complexity = TaskComplexityClassifier.classify(description)
        if complexity == TaskComplexity.COMPLEX:
            return TaskType.COMPLEX_REASONING

        # Topic-based routing
        topic = TopicExtractor.extract(description)
        return _TOPIC_TO_TASK_TYPE.get(topic, TaskType.SIMPLE_QA)

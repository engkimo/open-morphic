"""TaskComplexityClassifier — pure domain service for goal complexity assessment.

Classifies a goal string into SIMPLE / MEDIUM / COMPLEX based on heuristic
keyword and pattern analysis. No I/O, no LLM dependency.
"""

from __future__ import annotations

import re

from domain.value_objects.task_complexity import TaskComplexity

# Concern families: related terms grouped so "REST API" counts as 1 concern.
# 3+ families → COMPLEX, 2 families → MEDIUM.
_CONCERN_FAMILIES: list[set[str]] = [
    {"api", "rest", "graphql", "endpoint", "route"},
    {"database", "db", "sql", "migration", "schema"},
    {"auth", "authentication", "authorization", "login", "oauth"},
    {"test", "tests", "testing", "unittest", "pytest"},
    {"deploy", "deployment", "ci", "cd", "docker", "kubernetes"},
    {"frontend", "ui", "ux", "css", "html", "react", "vue"},
    {"backend", "server", "middleware"},
    {"security", "encryption", "csrf", "xss"},
    {"monitoring", "logging", "observability"},
    {"caching", "cache", "redis", "memcached"},
]

# Patterns that strongly indicate a simple, single-action task.
_SIMPLE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"^(write|implement|create|make|build|code|generate)\s+(a\s+)?"
        r"(function|class|method|script|program|module)",
        re.IGNORECASE,
    ),
    re.compile(r"^(fix|debug|solve|repair|correct)\b", re.IGNORECASE),
    re.compile(
        r"\b(fibonacci|fizzbuzz|fizz.?buzz|sort|search|factorial|palindrome"
        r"|prime|calculator|hello.?world|todo.?list|counter|timer)\b",
        re.IGNORECASE,
    ),
    re.compile(r"^(explain|describe|what\s+is|how\s+does|summarize)\b", re.IGNORECASE),
    re.compile(
        r"^(read|write|edit|delete|rename|move|copy)\s+(a\s+)?file\b",
        re.IGNORECASE,
    ),
]

# Patterns indicating architecture-level / multi-step work → COMPLEX.
_COMPLEX_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(refactor|migrate|rewrite|overhaul|redesign|re-?architect)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(full.?stack|end.?to.?end|e2e|microservice|monorepo)\b",
        re.IGNORECASE,
    ),
]


class TaskComplexityClassifier:
    """Classify goal text into SIMPLE / MEDIUM / COMPLEX.

    Pure static methods — no constructor state, no I/O.
    """

    @staticmethod
    def classify(goal: str) -> TaskComplexity:
        """Classify goal text into a complexity level."""
        text = goal.strip()

        # Very short goals are almost always simple
        if len(text) < 30:
            # Still check for multi-concern even in short text
            concerns = TaskComplexityClassifier._count_concerns(text)
            if concerns >= 2:
                return TaskComplexity.MEDIUM
            return TaskComplexity.SIMPLE

        # Check for explicit simple patterns
        for pattern in _SIMPLE_PATTERNS:
            if pattern.search(text):
                return TaskComplexity.SIMPLE

        # Count distinct software concerns
        concerns = TaskComplexityClassifier._count_concerns(text)
        if concerns >= 3:
            return TaskComplexity.COMPLEX

        # Check for complex architecture patterns
        for pattern in _COMPLEX_PATTERNS:
            if pattern.search(text):
                return TaskComplexity.COMPLEX

        if concerns == 2:
            return TaskComplexity.MEDIUM

        # Word count fallback
        word_count = len(text.split())
        if word_count <= 10:
            return TaskComplexity.SIMPLE
        if word_count <= 25:
            return TaskComplexity.MEDIUM

        return TaskComplexity.COMPLEX

    @staticmethod
    def recommended_subtask_range(complexity: TaskComplexity) -> tuple[int, int]:
        """Return (min, max) subtask count for given complexity."""
        return {
            TaskComplexity.SIMPLE: (1, 1),
            TaskComplexity.MEDIUM: (2, 3),
            TaskComplexity.COMPLEX: (3, 5),
        }[complexity]

    @staticmethod
    def _count_concerns(text: str) -> int:
        """Count distinct concern families represented in text."""
        lower = text.lower()
        tokens = set(re.findall(r"[a-z]+", lower))
        count = 0
        for family in _CONCERN_FAMILIES:
            if tokens & family:
                count += 1
        return count

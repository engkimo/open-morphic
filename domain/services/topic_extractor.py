"""TopicExtractor — Pure domain service for extracting normalized topics from task text.

Pure static service. Uses keyword matching to classify task text into a normalized
topic string. Falls back to "general". Used by RouteToEngineUseCase to query/update
affinity scores.
"""

from __future__ import annotations

import re

# Topic keyword map: topic → list of keywords/phrases
_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "frontend": [
        "react",
        "vue",
        "angular",
        "css",
        "html",
        "tailwind",
        "next.js",
        "nextjs",
        "svelte",
        "ui component",
        "frontend",
        "front-end",
        "stylesheet",
        "responsive",
    ],
    "backend": [
        "fastapi",
        "django",
        "flask",
        "express",
        "api endpoint",
        "rest api",
        "graphql",
        "server",
        "backend",
        "back-end",
        "middleware",
    ],
    "database": [
        "sql",
        "postgresql",
        "postgres",
        "mysql",
        "mongodb",
        "redis",
        "database",
        "migration",
        "schema",
        "query",
        "orm",
        "sqlalchemy",
        "prisma",
    ],
    "devops": [
        "docker",
        "kubernetes",
        "k8s",
        "ci/cd",
        "cicd",
        "github actions",
        "terraform",
        "ansible",
        "deploy",
        "deployment",
        "infrastructure",
        "nginx",
        "aws",
        "gcp",
        "azure",
    ],
    "testing": [
        "test",
        "pytest",
        "jest",
        "unittest",
        "coverage",
        "tdd",
        "integration test",
        "e2e test",
        "mock",
        "fixture",
    ],
    "security": [
        "security",
        "authentication",
        "authorization",
        "oauth",
        "jwt",
        "encryption",
        "xss",
        "csrf",
        "vulnerability",
        "penetration",
    ],
    "ml": [
        "machine learning",
        "deep learning",
        "neural network",
        "pytorch",
        "tensorflow",
        "model training",
        "llm",
        "embeddings",
        "fine-tuning",
        "fine tuning",
        "nlp",
        "transformer",
    ],
    "data": [
        "data pipeline",
        "etl",
        "data analysis",
        "pandas",
        "spark",
        "airflow",
        "data warehouse",
        "analytics",
        "visualization",
        "csv",
        "parquet",
    ],
    "documentation": [
        "documentation",
        "readme",
        "docstring",
        "api docs",
        "changelog",
        "architecture doc",
        "technical writing",
    ],
    "refactoring": [
        "refactor",
        "clean up",
        "reorganize",
        "restructure",
        "simplify",
        "optimize",
        "performance",
        "code quality",
    ],
}

# Pre-compile patterns for efficient matching
_COMPILED_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    topic: [re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE) for kw in keywords]
    for topic, keywords in _TOPIC_KEYWORDS.items()
}


class TopicExtractor:
    """Extract a normalized topic from task text using keyword matching."""

    @staticmethod
    def extract(text: str) -> str:
        """Extract the best-matching topic from task text.

        Returns the topic with the most keyword matches, or "general" if none match.
        """
        if not text or not text.strip():
            return "general"

        scores: dict[str, int] = {}
        for topic, patterns in _COMPILED_PATTERNS.items():
            count = sum(1 for p in patterns if p.search(text))
            if count > 0:
                scores[topic] = count

        if not scores:
            return "general"

        return max(scores, key=scores.get)  # type: ignore[arg-type]

    @staticmethod
    def known_topics() -> list[str]:
        """Return all known topic names."""
        return sorted(_TOPIC_KEYWORDS.keys())

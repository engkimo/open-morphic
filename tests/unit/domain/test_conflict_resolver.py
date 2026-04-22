"""Tests for ConflictResolver domain service."""

from __future__ import annotations

import pytest

from domain.ports.insight_extractor import ExtractedInsight
from domain.services.conflict_resolver import ConflictResolver
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.cognitive import CognitiveMemoryType


def _make(
    content: str,
    engine: AgentEngineType = AgentEngineType.CLAUDE_CODE,
    confidence: float = 0.7,
) -> ExtractedInsight:
    return ExtractedInsight(
        content=content,
        memory_type=CognitiveMemoryType.SEMANTIC,
        confidence=confidence,
        source_engine=engine,
        tags=[],
    )


class TestDetectConflicts:
    """ConflictResolver.detect_conflicts — pairwise conflict detection."""

    def test_no_insights(self) -> None:
        assert ConflictResolver.detect_conflicts([]) == []

    def test_single_insight_no_conflict(self) -> None:
        assert ConflictResolver.detect_conflicts([_make("uses Redis")]) == []

    def test_same_engine_never_conflicts(self) -> None:
        a = _make("project uses Redis", engine=AgentEngineType.CLAUDE_CODE)
        b = _make("project does not use Redis", engine=AgentEngineType.CLAUDE_CODE)
        assert ConflictResolver.detect_conflicts([a, b]) == []

    def test_no_overlap_no_conflict(self) -> None:
        a = _make("project uses Redis", engine=AgentEngineType.CLAUDE_CODE)
        b = _make("weather is sunny today not cold", engine=AgentEngineType.GEMINI_CLI)
        assert ConflictResolver.detect_conflicts([a, b]) == []

    def test_overlap_without_negation_no_conflict(self) -> None:
        a = _make("project uses Redis for caching", engine=AgentEngineType.CLAUDE_CODE)
        b = _make("project uses Redis for sessions", engine=AgentEngineType.GEMINI_CLI)
        assert ConflictResolver.detect_conflicts([a, b]) == []

    def test_negation_on_both_sides_no_conflict(self) -> None:
        a = _make("project does not use Redis", engine=AgentEngineType.CLAUDE_CODE)
        b = _make("project does not use Redis cache", engine=AgentEngineType.GEMINI_CLI)
        assert ConflictResolver.detect_conflicts([a, b]) == []

    def test_real_conflict_detected(self) -> None:
        a = _make(
            "project uses Redis for caching",
            engine=AgentEngineType.CLAUDE_CODE,
        )
        b = _make(
            "project does not use Redis for caching",
            engine=AgentEngineType.GEMINI_CLI,
        )
        conflicts = ConflictResolver.detect_conflicts([a, b])
        assert len(conflicts) == 1
        assert conflicts[0].overlap_score >= 0.4

    def test_conflict_pair_has_winner(self) -> None:
        a = _make(
            "project uses Redis",
            engine=AgentEngineType.CLAUDE_CODE,
            confidence=0.9,
        )
        b = _make(
            "project does not use Redis",
            engine=AgentEngineType.GEMINI_CLI,
            confidence=0.5,
        )
        conflicts = ConflictResolver.detect_conflicts([a, b])
        assert len(conflicts) == 1
        assert conflicts[0].resolved_winner is a

    def test_multiple_conflicts(self) -> None:
        a = _make(
            "project uses Redis cache",
            engine=AgentEngineType.CLAUDE_CODE,
            confidence=0.8,
        )
        b = _make(
            "project does not use Redis cache",
            engine=AgentEngineType.GEMINI_CLI,
        )
        c = _make(
            "deploy app server locally",
            engine=AgentEngineType.CODEX_CLI,
            confidence=0.6,
        )
        d = _make(
            "never deploy app server locally",
            engine=AgentEngineType.OLLAMA,
            confidence=0.4,
        )
        conflicts = ConflictResolver.detect_conflicts([a, b, c, d])
        assert len(conflicts) == 2

    def test_low_overlap_below_threshold(self) -> None:
        a = _make("Redis caching layer design", engine=AgentEngineType.CLAUDE_CODE)
        b = _make("not a good design pattern for database", engine=AgentEngineType.GEMINI_CLI)
        assert ConflictResolver.detect_conflicts([a, b]) == []


class TestResolve:
    """ConflictResolver.resolve — higher confidence wins."""

    def test_higher_confidence_wins(self) -> None:
        a = _make("X", confidence=0.9)
        b = _make("Y", confidence=0.5)
        assert ConflictResolver.resolve(a, b) is a

    def test_lower_confidence_loses(self) -> None:
        a = _make("X", confidence=0.3)
        b = _make("Y", confidence=0.8)
        assert ConflictResolver.resolve(a, b) is b

    def test_tie_first_wins(self) -> None:
        a = _make("X", confidence=0.7)
        b = _make("Y", confidence=0.7)
        assert ConflictResolver.resolve(a, b) is a


class TestResolveAll:
    """ConflictResolver.resolve_all — removes losers, returns survivors."""

    def test_no_conflicts_all_survive(self) -> None:
        insights = [
            _make("alpha", engine=AgentEngineType.CLAUDE_CODE),
            _make("beta", engine=AgentEngineType.GEMINI_CLI),
        ]
        survivors, conflicts = ConflictResolver.resolve_all(insights)
        assert len(survivors) == 2
        assert conflicts == []

    def test_loser_removed(self) -> None:
        a = _make(
            "project uses Redis cache",
            engine=AgentEngineType.CLAUDE_CODE,
            confidence=0.9,
        )
        b = _make(
            "project does not use Redis cache",
            engine=AgentEngineType.GEMINI_CLI,
            confidence=0.4,
        )
        survivors, conflicts = ConflictResolver.resolve_all([a, b])
        assert len(survivors) == 1
        assert survivors[0] is a
        assert len(conflicts) == 1

    def test_empty_list(self) -> None:
        survivors, conflicts = ConflictResolver.resolve_all([])
        assert survivors == []
        assert conflicts == []

    def test_non_conflicting_preserved(self) -> None:
        a = _make(
            "project uses Redis cache",
            engine=AgentEngineType.CLAUDE_CODE,
            confidence=0.9,
        )
        b = _make(
            "project does not use Redis cache",
            engine=AgentEngineType.GEMINI_CLI,
            confidence=0.4,
        )
        c = _make("weather is nice", engine=AgentEngineType.CODEX_CLI)
        survivors, conflicts = ConflictResolver.resolve_all([a, b, c])
        assert len(survivors) == 2
        assert a in survivors
        assert c in survivors

    def test_multiple_conflicts_resolved(self) -> None:
        a = _make(
            "project uses Redis cache",
            engine=AgentEngineType.CLAUDE_CODE,
            confidence=0.8,
        )
        b = _make(
            "project does not use Redis cache",
            engine=AgentEngineType.GEMINI_CLI,
            confidence=0.3,
        )
        c = _make(
            "deploy app server locally",
            engine=AgentEngineType.CODEX_CLI,
            confidence=0.6,
        )
        d = _make(
            "never deploy app server locally",
            engine=AgentEngineType.OLLAMA,
            confidence=0.4,
        )
        survivors, conflicts = ConflictResolver.resolve_all([a, b, c, d])
        assert len(conflicts) == 2
        assert a in survivors
        assert c in survivors
        assert b not in survivors
        assert d not in survivors


class TestTokenizeHelpers:
    """Internal helper coverage."""

    def test_stopwords_excluded(self) -> None:
        tokens = ConflictResolver._tokenize("the project is a service")
        assert "the" not in tokens
        assert "is" not in tokens
        assert "a" not in tokens
        assert "project" in tokens

    def test_negation_words_excluded(self) -> None:
        tokens = ConflictResolver._tokenize("not replaced without removed")
        assert len(tokens) == 0

    def test_has_negation_true(self) -> None:
        assert ConflictResolver._has_negation("this is not working") is True

    def test_has_negation_false(self) -> None:
        assert ConflictResolver._has_negation("this is working fine") is False

    def test_jaccard_empty_sets(self) -> None:
        assert ConflictResolver._jaccard(set(), set()) == 0.0

    def test_jaccard_identical(self) -> None:
        s = {"a", "b", "c"}
        assert ConflictResolver._jaccard(s, s) == pytest.approx(1.0)

    def test_jaccard_disjoint(self) -> None:
        assert ConflictResolver._jaccard({"a"}, {"b"}) == pytest.approx(0.0)

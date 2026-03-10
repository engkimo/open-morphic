"""Conflict resolver — detects and resolves contradictions between insights.

Pure static domain service.  No external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.ports.insight_extractor import ExtractedInsight

_NEGATION_WORDS: frozenset[str] = frozenset(
    {
        "not",
        "never",
        "instead",
        "replaced",
        "don't",
        "dont",
        "doesn't",
        "doesnt",
        "shouldn't",
        "shouldnt",
        "cannot",
        "can't",
        "cant",
        "no",
        "without",
        "removed",
        "deprecated",
    }
)

_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "it",
        "and",
        "or",
        "but",
        "this",
        "that",
        "from",
        "as",
    }
)


@dataclass(frozen=True)
class ConflictPair:
    """A detected conflict between two insights."""

    insight_a: ExtractedInsight
    insight_b: ExtractedInsight
    overlap_score: float
    resolved_winner: ExtractedInsight


class ConflictResolver:
    """Detect and resolve contradictions between :class:`ExtractedInsight` items."""

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Lowercase tokens excluding stopwords and negation words."""
        return {w for w in text.lower().split() if w not in _STOPWORDS and w not in _NEGATION_WORDS}

    @staticmethod
    def _has_negation(text: str) -> bool:
        words = set(text.lower().split())
        return bool(words & _NEGATION_WORDS)

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a and not b:
            return 0.0
        return len(a & b) / len(a | b)

    @classmethod
    def _is_conflict(cls, a: ExtractedInsight, b: ExtractedInsight) -> tuple[bool, float]:
        """Return (is_conflict, overlap_score)."""
        # Criterion 1: different source engines
        if a.source_engine == b.source_engine:
            return False, 0.0

        tokens_a = cls._tokenize(a.content)
        tokens_b = cls._tokenize(b.content)
        overlap = cls._jaccard(tokens_a, tokens_b)

        # Criterion 2: keyword overlap >= 0.4
        if overlap < 0.4:
            return False, overlap

        # Criterion 3: exactly one side contains negation
        neg_a = cls._has_negation(a.content)
        neg_b = cls._has_negation(b.content)
        if neg_a == neg_b:
            return False, overlap

        return True, overlap

    @classmethod
    def detect_conflicts(cls, insights: list[ExtractedInsight]) -> list[ConflictPair]:
        """Pairwise conflict detection.  O(n^2) — fine for typical small lists."""
        conflicts: list[ConflictPair] = []
        seen: set[tuple[int, int]] = set()

        for i, a in enumerate(insights):
            for j, b in enumerate(insights):
                if i >= j or (i, j) in seen:
                    continue
                is_conflict, overlap = cls._is_conflict(a, b)
                if is_conflict:
                    winner = cls.resolve(a, b)
                    conflicts.append(
                        ConflictPair(
                            insight_a=a,
                            insight_b=b,
                            overlap_score=overlap,
                            resolved_winner=winner,
                        )
                    )
                    seen.add((i, j))
        return conflicts

    @staticmethod
    def resolve(a: ExtractedInsight, b: ExtractedInsight) -> ExtractedInsight:
        """Higher confidence wins.  Tie → first argument wins (stable)."""
        if a.confidence >= b.confidence:
            return a
        return b

    @classmethod
    def resolve_all(
        cls, insights: list[ExtractedInsight]
    ) -> tuple[list[ExtractedInsight], list[ConflictPair]]:
        """Remove losers from *insights* and return survivors + conflict log."""
        conflicts = cls.detect_conflicts(insights)

        # Collect losing insights (by identity)
        losers: set[int] = set()
        for cp in conflicts:
            loser = cp.insight_b if cp.resolved_winner is cp.insight_a else cp.insight_a
            for idx, ins in enumerate(insights):
                if ins is loser:
                    losers.add(idx)
                    break

        survivors = [ins for idx, ins in enumerate(insights) if idx not in losers]
        return survivors, conflicts

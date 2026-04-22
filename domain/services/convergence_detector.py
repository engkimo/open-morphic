"""Convergence detector — determines when iterative discussion has stabilized.

Pure static domain service.  No external dependencies.

Sprint 13.5 (TD-091): Adaptive discussion strategy — dynamic round count
based on convergence detection between consecutive discussion rounds.
"""

from __future__ import annotations

from dataclasses import dataclass

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

_AGREEMENT_SIGNALS: frozenset[str] = frozenset(
    {
        "agree",
        "agrees",
        "agreed",
        "confirm",
        "confirms",
        "confirmed",
        "correct",
        "accurate",
        "consistent",
        "aligns",
        "aligned",
        "matches",
        "identical",
        "same",
        "unchanged",
        "no changes",
        "no issues",
        "no corrections",
        "no modifications",
        "well-structured",
        "comprehensive",
        "thorough",
        "complete",
        "sufficient",
        "adequate",
        "合意",
        "一致",
        "同意",
        "正しい",
        "変更なし",
        "修正なし",
        "問題なし",
    }
)

_DIVERGENCE_SIGNALS: frozenset[str] = frozenset(
    {
        "disagree",
        "incorrect",
        "wrong",
        "error",
        "mistake",
        "however",
        "instead",
        "alternatively",
        "reconsider",
        "overlooked",
        "missed",
        "flawed",
        "insufficient",
        "incomplete",
        "contradicts",
        "contradiction",
        "反対",
        "誤り",
        "間違い",
        "不十分",
        "矛盾",
        "修正が必要",
        "再検討",
    }
)


@dataclass(frozen=True)
class ConvergenceResult:
    """Result of convergence detection between two consecutive rounds."""

    converged: bool
    similarity: float
    agreement_score: float
    divergence_score: float
    signals: list[str]


class ConvergenceDetector:
    """Detect convergence between consecutive discussion round outputs.

    Uses three signals:
    1. Jaccard word overlap between consecutive round texts
    2. Agreement keyword density (signals that the critic agrees)
    3. Divergence keyword density (signals that the critic disagrees)

    The final decision combines these: high similarity + high agreement
    + low divergence = converged.
    """

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Lowercase content tokens excluding stopwords."""
        return {w for w in text.lower().split() if w not in _STOPWORDS and len(w) > 1}

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a and not b:
            return 1.0  # Two empty texts are identical
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    @classmethod
    def _signal_density(cls, text: str, signals: frozenset[str]) -> float:
        """Fraction of signal phrases found in text (0.0 to 1.0)."""
        if not text:
            return 0.0
        lower = text.lower()
        found = sum(1 for s in signals if s in lower)
        return min(found / max(len(signals) * 0.1, 1.0), 1.0)

    @classmethod
    def detect(
        cls,
        previous_text: str,
        current_text: str,
        threshold: float = 0.85,
    ) -> ConvergenceResult:
        """Determine if discussion has converged between two consecutive rounds.

        Parameters
        ----------
        previous_text:
            Output from the previous discussion round.
        current_text:
            Output from the current discussion round.
        threshold:
            Jaccard similarity threshold for convergence (0.0-1.0).

        Returns
        -------
        ConvergenceResult with convergence decision and diagnostic signals.
        """
        tokens_prev = cls._tokenize(previous_text)
        tokens_curr = cls._tokenize(current_text)
        similarity = cls._jaccard(tokens_prev, tokens_curr)

        agreement = cls._signal_density(current_text, _AGREEMENT_SIGNALS)
        divergence = cls._signal_density(current_text, _DIVERGENCE_SIGNALS)

        signals: list[str] = []

        # Signal 1: High text overlap
        if similarity >= threshold:
            signals.append(f"high_similarity={similarity:.3f}")

        # Signal 2: Agreement keywords present
        if agreement > 0.1:
            signals.append(f"agreement_detected={agreement:.3f}")

        # Signal 3: Divergence keywords present
        if divergence > 0.1:
            signals.append(f"divergence_detected={divergence:.3f}")

        # Signal 4: Substantial length change suggests non-convergence
        len_prev = len(previous_text)
        len_curr = len(current_text)
        if len_prev > 0:
            length_ratio = min(len_prev, len_curr) / max(len_prev, len_curr)
            if length_ratio < 0.5:
                signals.append(f"length_shift={length_ratio:.3f}")

        # Convergence decision: weighted combination
        # High similarity is the primary signal.
        # Agreement boosts convergence, divergence suppresses it.
        effective_score = similarity + (agreement * 0.15) - (divergence * 0.2)
        converged = effective_score >= threshold

        return ConvergenceResult(
            converged=converged,
            similarity=similarity,
            agreement_score=agreement,
            divergence_score=divergence,
            signals=signals,
        )

    @classmethod
    def should_continue(
        cls,
        rounds_completed: int,
        min_rounds: int,
        max_rounds: int,
        previous_text: str | None,
        current_text: str | None,
        threshold: float = 0.85,
    ) -> tuple[bool, ConvergenceResult | None]:
        """High-level decision: should the discussion continue?

        Returns (should_continue, convergence_result).

        Rules:
        1. Always continue if rounds_completed < min_rounds
        2. Always stop if rounds_completed >= max_rounds
        3. Between min and max: stop if converged
        """
        if rounds_completed >= max_rounds:
            return False, None

        if rounds_completed < min_rounds:
            return True, None

        if previous_text is None or current_text is None:
            return True, None

        result = cls.detect(previous_text, current_text, threshold)
        return not result.converged, result

"""Tests for ConvergenceDetector — Sprint 13.5 (TD-091).

Pure domain service: no I/O, no mocks, no external dependencies.
"""

from __future__ import annotations

import pytest

from domain.services.convergence_detector import ConvergenceDetector, ConvergenceResult


class TestDetect:
    """Test ConvergenceDetector.detect() — core convergence detection."""

    def test_identical_texts_converge(self) -> None:
        text = "The weather in Tokyo is sunny with 25 degrees and low humidity."
        result = ConvergenceDetector.detect(text, text)
        assert result.converged is True
        assert result.similarity == 1.0

    def test_very_similar_texts_converge(self) -> None:
        prev = "Tokyo weather: sunny, 25 degrees, low humidity expected today."
        curr = "Tokyo weather: sunny, 25 degrees, low humidity expected today. Overall clear."
        result = ConvergenceDetector.detect(prev, curr, threshold=0.7)
        assert result.converged is True
        assert result.similarity > 0.7

    def test_completely_different_texts_do_not_converge(self) -> None:
        prev = "The cat sat on the mat and looked out the window."
        curr = "Quantum computing leverages superposition for parallel calculations."
        result = ConvergenceDetector.detect(prev, curr)
        assert result.converged is False
        assert result.similarity < 0.3

    def test_agreement_signals_boost_convergence(self) -> None:
        prev = "Analysis shows the optimal solution requires three database shards."
        curr = (
            "I agree the analysis is correct and confirmed. "
            "The optimal solution requires three database shards."
        )
        result = ConvergenceDetector.detect(prev, curr, threshold=0.8)
        assert result.agreement_score > 0.0
        # Agreement boost can push borderline cases over threshold
        assert any("agreement_detected" in s for s in result.signals)

    def test_divergence_signals_suppress_convergence(self) -> None:
        prev = "We should use PostgreSQL for the primary database."
        curr = (
            "I disagree — PostgreSQL is incorrect for this use case. "
            "Instead, we should reconsider using MongoDB. The previous analysis was flawed."
        )
        result = ConvergenceDetector.detect(prev, curr, threshold=0.5)
        assert result.divergence_score > 0.0
        assert any("divergence_detected" in s for s in result.signals)

    def test_empty_texts_converge(self) -> None:
        result = ConvergenceDetector.detect("", "")
        assert result.converged is True
        assert result.similarity == 1.0

    def test_one_empty_does_not_converge(self) -> None:
        result = ConvergenceDetector.detect("", "some content here")
        assert result.converged is False
        assert result.similarity == 0.0

    def test_threshold_respected(self) -> None:
        prev = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        curr = "alpha beta gamma delta epsilon zeta eta theta lambda mu"
        # 80% overlap
        result_low = ConvergenceDetector.detect(prev, curr, threshold=0.5)
        result_high = ConvergenceDetector.detect(prev, curr, threshold=0.95)
        assert result_low.converged is True
        assert result_high.converged is False

    def test_returns_convergence_result_type(self) -> None:
        result = ConvergenceDetector.detect("hello world", "hello world")
        assert isinstance(result, ConvergenceResult)
        assert isinstance(result.converged, bool)
        assert isinstance(result.similarity, float)
        assert isinstance(result.agreement_score, float)
        assert isinstance(result.divergence_score, float)
        assert isinstance(result.signals, list)

    def test_length_shift_signal_on_large_change(self) -> None:
        prev = "Short text."
        curr = "A " * 200 + "much longer text with many tokens."
        result = ConvergenceDetector.detect(prev, curr)
        assert any("length_shift" in s for s in result.signals)

    def test_japanese_agreement_signals(self) -> None:
        prev = "東京の天気は晴れで気温は25度です。"
        curr = "前の分析と一致しています。東京の天気は晴れで気温は25度で、問題なしです。"
        result = ConvergenceDetector.detect(prev, curr, threshold=0.3)
        assert result.agreement_score > 0.0

    def test_japanese_divergence_signals(self) -> None:
        prev = "PostgreSQLを使うべきです。"
        curr = "それは誤りです。MongoDBの方が適切で、矛盾があります。再検討が必要です。"
        result = ConvergenceDetector.detect(prev, curr, threshold=0.3)
        assert result.divergence_score > 0.0

    def test_similarity_is_symmetric(self) -> None:
        a = "The quick brown fox jumps over the lazy dog near the river bank."
        b = "A quick red fox leaps across the lazy hound near the river bank."
        r1 = ConvergenceDetector.detect(a, b)
        r2 = ConvergenceDetector.detect(b, a)
        assert r1.similarity == pytest.approx(r2.similarity)

    def test_high_similarity_signal_label(self) -> None:
        text = "identical content here with enough tokens to be meaningful"
        result = ConvergenceDetector.detect(text, text)
        assert any("high_similarity" in s for s in result.signals)


class TestShouldContinue:
    """Test ConvergenceDetector.should_continue() — high-level decision logic."""

    def test_below_min_rounds_always_continues(self) -> None:
        cont, result = ConvergenceDetector.should_continue(
            rounds_completed=1,
            min_rounds=2,
            max_rounds=5,
            previous_text="identical",
            current_text="identical",
        )
        assert cont is True
        assert result is None  # No check performed below min_rounds

    def test_at_max_rounds_always_stops(self) -> None:
        cont, result = ConvergenceDetector.should_continue(
            rounds_completed=5,
            min_rounds=1,
            max_rounds=5,
            previous_text="different text",
            current_text="completely other content",
        )
        assert cont is False
        assert result is None

    def test_converged_between_min_and_max_stops(self) -> None:
        text = "the analysis shows consistent results across all models"
        cont, result = ConvergenceDetector.should_continue(
            rounds_completed=2,
            min_rounds=1,
            max_rounds=5,
            previous_text=text,
            current_text=text,
        )
        assert cont is False
        assert result is not None
        assert result.converged is True

    def test_not_converged_between_min_and_max_continues(self) -> None:
        cont, result = ConvergenceDetector.should_continue(
            rounds_completed=2,
            min_rounds=1,
            max_rounds=5,
            previous_text="Analysis suggests using Redis for caching layer implementation.",
            current_text="Quantum physics describes particle behavior at subatomic scales.",
        )
        assert cont is True
        assert result is not None
        assert result.converged is False

    def test_none_previous_text_continues(self) -> None:
        cont, result = ConvergenceDetector.should_continue(
            rounds_completed=2,
            min_rounds=1,
            max_rounds=5,
            previous_text=None,
            current_text="some text",
        )
        assert cont is True
        assert result is None

    def test_none_current_text_continues(self) -> None:
        cont, result = ConvergenceDetector.should_continue(
            rounds_completed=2,
            min_rounds=1,
            max_rounds=5,
            previous_text="some text",
            current_text=None,
        )
        assert cont is True
        assert result is None

    def test_min_equals_max_stops_at_max(self) -> None:
        cont, result = ConvergenceDetector.should_continue(
            rounds_completed=3,
            min_rounds=3,
            max_rounds=3,
            previous_text="text a",
            current_text="text b",
        )
        assert cont is False

    def test_threshold_passed_through(self) -> None:
        """Custom threshold is used in convergence detection."""
        text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        # Very strict threshold — even identical text might need exact match
        cont, result = ConvergenceDetector.should_continue(
            rounds_completed=2,
            min_rounds=1,
            max_rounds=5,
            previous_text=text,
            current_text=text,
            threshold=0.99,
        )
        assert cont is False  # Identical texts always converge
        assert result is not None
        assert result.similarity == 1.0


class TestTokenize:
    """Test internal tokenization."""

    def test_removes_stopwords(self) -> None:
        tokens = ConvergenceDetector._tokenize("the quick fox is on a hill")
        assert "the" not in tokens
        assert "is" not in tokens
        assert "on" not in tokens
        assert "quick" in tokens
        assert "fox" in tokens
        assert "hill" in tokens

    def test_lowercase(self) -> None:
        tokens = ConvergenceDetector._tokenize("Tokyo Weather SUNNY")
        assert "tokyo" in tokens
        assert "weather" in tokens
        assert "sunny" in tokens

    def test_removes_single_char_tokens(self) -> None:
        tokens = ConvergenceDetector._tokenize("I x y hello world")
        assert "x" not in tokens
        assert "y" not in tokens
        assert "hello" in tokens

    def test_empty_string(self) -> None:
        tokens = ConvergenceDetector._tokenize("")
        assert tokens == set()


class TestJaccard:
    """Test Jaccard similarity."""

    def test_identical_sets(self) -> None:
        assert ConvergenceDetector._jaccard({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint_sets(self) -> None:
        assert ConvergenceDetector._jaccard({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self) -> None:
        # {a,b,c} ∩ {b,c,d} = {b,c}, union = {a,b,c,d}
        assert ConvergenceDetector._jaccard({"a", "b", "c"}, {"b", "c", "d"}) == pytest.approx(0.5)

    def test_both_empty(self) -> None:
        assert ConvergenceDetector._jaccard(set(), set()) == 1.0

    def test_one_empty(self) -> None:
        assert ConvergenceDetector._jaccard(set(), {"a"}) == 0.0


class TestSignalDensity:
    """Test signal density calculation."""

    def test_no_signals_returns_zero(self) -> None:
        from domain.services.convergence_detector import _AGREEMENT_SIGNALS

        density = ConvergenceDetector._signal_density("random text here", _AGREEMENT_SIGNALS)
        assert density == 0.0

    def test_multiple_signals_returns_positive(self) -> None:
        from domain.services.convergence_detector import _AGREEMENT_SIGNALS

        text = "I agree the result is correct and confirmed accurate."
        density = ConvergenceDetector._signal_density(text, _AGREEMENT_SIGNALS)
        assert density > 0.0

    def test_empty_text_returns_zero(self) -> None:
        from domain.services.convergence_detector import _AGREEMENT_SIGNALS

        density = ConvergenceDetector._signal_density("", _AGREEMENT_SIGNALS)
        assert density == 0.0

    def test_density_capped_at_one(self) -> None:
        from domain.services.convergence_detector import _AGREEMENT_SIGNALS

        # Pack all signals into one text
        text = " ".join(_AGREEMENT_SIGNALS)
        density = ConvergenceDetector._signal_density(text, _AGREEMENT_SIGNALS)
        assert density <= 1.0

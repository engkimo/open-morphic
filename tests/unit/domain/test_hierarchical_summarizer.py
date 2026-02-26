"""Tests for domain/services/hierarchical_summarizer.py.

Pure logic tests — no I/O, no async.
"""

from __future__ import annotations

from domain.services.hierarchical_summarizer import HierarchicalSummarizer


# ── estimate_tokens ──


class TestEstimateTokens:
    def test_empty_string(self) -> None:
        assert HierarchicalSummarizer.estimate_tokens("") == 0

    def test_short_text(self) -> None:
        # "hello" = 5 chars => 5//4 = 1
        assert HierarchicalSummarizer.estimate_tokens("hello") == 1

    def test_long_text(self) -> None:
        text = "a" * 400
        assert HierarchicalSummarizer.estimate_tokens(text) == 100

    def test_unicode(self) -> None:
        text = "日本語テスト"  # 6 chars => 6//4 = 1
        result = HierarchicalSummarizer.estimate_tokens(text)
        assert result >= 1


# ── split_sentences ──


class TestSplitSentences:
    def test_single_sentence(self) -> None:
        result = HierarchicalSummarizer.split_sentences("Hello world.")
        assert result == ["Hello world."]

    def test_multiple_sentences(self) -> None:
        text = "First sentence. Second sentence. Third sentence."
        result = HierarchicalSummarizer.split_sentences(text)
        assert len(result) == 3
        assert result[0] == "First sentence."
        assert result[1] == "Second sentence."
        assert result[2] == "Third sentence."

    def test_newlines(self) -> None:
        text = "Line one\nLine two\nLine three"
        result = HierarchicalSummarizer.split_sentences(text)
        assert len(result) == 3

    def test_no_period(self) -> None:
        result = HierarchicalSummarizer.split_sentences("No period here")
        assert result == ["No period here"]

    def test_empty(self) -> None:
        assert HierarchicalSummarizer.split_sentences("") == []

    def test_whitespace_only(self) -> None:
        assert HierarchicalSummarizer.split_sentences("   ") == []


# ── extract_summary ──


class TestExtractSummary:
    def test_full_ratio(self) -> None:
        text = "First. Second. Third."
        result = HierarchicalSummarizer.extract_summary(text, 1.0)
        assert "First." in result
        assert "Second." in result
        assert "Third." in result

    def test_half_ratio(self) -> None:
        text = "One. Two. Three. Four."
        result = HierarchicalSummarizer.extract_summary(text, 0.5)
        # 4 sentences * 0.5 = 2 => ceil(2) = 2
        assert "One." in result
        assert "Two." in result
        assert "Three." not in result

    def test_minimal_ratio(self) -> None:
        text = "One. Two. Three. Four. Five."
        result = HierarchicalSummarizer.extract_summary(text, 0.05)
        # 5 * 0.05 = 0.25 => ceil = 1
        sentences = HierarchicalSummarizer.split_sentences(result)
        assert len(sentences) >= 1

    def test_single_sentence_content(self) -> None:
        text = "Only one sentence here."
        result = HierarchicalSummarizer.extract_summary(text, 0.1)
        assert "Only one sentence here." in result

    def test_empty_content(self) -> None:
        assert HierarchicalSummarizer.extract_summary("", 0.5) == ""


# ── build_extractive_hierarchy ──


class TestBuildExtractiveHierarchy:
    def test_four_levels_exist(self) -> None:
        text = "A. B. C. D. E. F. G. H. I. J."
        hierarchy = HierarchicalSummarizer.build_extractive_hierarchy(text)
        assert set(hierarchy.keys()) == {0, 1, 2, 3}

    def test_level0_is_original(self) -> None:
        text = "Original full text with many details."
        hierarchy = HierarchicalSummarizer.build_extractive_hierarchy(text)
        assert hierarchy[0] == text

    def test_level3_shortest(self) -> None:
        text = "A. B. C. D. E. F. G. H. I. J. K. L. M. N. O. P. Q. R. S. T."
        hierarchy = HierarchicalSummarizer.build_extractive_hierarchy(text)
        assert len(hierarchy[3]) <= len(hierarchy[2])
        assert len(hierarchy[2]) <= len(hierarchy[1])
        assert len(hierarchy[1]) <= len(hierarchy[0])

    def test_monotonic_decrease(self) -> None:
        text = ". ".join(f"Sentence {i}" for i in range(30)) + "."
        hierarchy = HierarchicalSummarizer.build_extractive_hierarchy(text)
        tokens = [HierarchicalSummarizer.estimate_tokens(hierarchy[level]) for level in range(4)]
        # Each level should have <= tokens of the previous
        for i in range(1, 4):
            assert tokens[i] <= tokens[i - 1]


# ── select_level ──


class TestSelectLevel:
    def test_all_fit_returns_level0(self) -> None:
        counts = {0: 100, 1: 40, 2: 15, 3: 5}
        assert HierarchicalSummarizer.select_level(counts, max_tokens=200) == 0

    def test_none_fit_returns_level3(self) -> None:
        counts = {0: 1000, 1: 400, 2: 150, 3: 50}
        assert HierarchicalSummarizer.select_level(counts, max_tokens=10) == 3

    def test_exact_fit(self) -> None:
        counts = {0: 100, 1: 40, 2: 15, 3: 5}
        assert HierarchicalSummarizer.select_level(counts, max_tokens=40) == 1

    def test_mid_budget(self) -> None:
        counts = {0: 500, 1: 200, 2: 75, 3: 25}
        # Budget 100 => L0 too big, L1 too big, L2=75 fits
        assert HierarchicalSummarizer.select_level(counts, max_tokens=100) == 2


# ── estimate_depth ──


class TestEstimateDepth:
    def test_large_budget_returns_level0(self) -> None:
        # Budget 1000, entry 100 => ratio 10.0 >= 1.0
        assert HierarchicalSummarizer.estimate_depth(1000, 100) == 0

    def test_small_budget_returns_level3(self) -> None:
        # Budget 5, entry 1000 => ratio 0.005 < 0.05
        assert HierarchicalSummarizer.estimate_depth(5, 1000) == 3

    def test_medium_budget(self) -> None:
        # Budget 200, entry 1000 => ratio 0.20 >= 0.15
        assert HierarchicalSummarizer.estimate_depth(200, 1000) == 2

    def test_zero_entry_tokens_returns_level0(self) -> None:
        assert HierarchicalSummarizer.estimate_depth(100, 0) == 0

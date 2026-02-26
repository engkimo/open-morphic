"""HierarchicalSummarizer — multi-level tree compression.

Pure domain service: no I/O, no external deps beyond stdlib.
All methods are static — follows DeltaEncoder/ForgettingCurve pattern.

Builds 4-level extractive summaries from text:
  Level 0 (leaf): original text (100%)
  Level 1:        ~40% of sentences
  Level 2:        ~15% of sentences
  Level 3 (root): ~5% of sentences (always at least 1)

Query-adaptive retrieval: pick the deepest level that fits within a token budget.
"""

from __future__ import annotations

import math
import re


class HierarchicalSummarizer:
    """Static methods for multi-level tree compression — no state, pure functions."""

    NUM_LEVELS: int = 4  # 0..3
    LEVEL_RATIOS: dict[int, float] = {0: 1.0, 1: 0.40, 2: 0.15, 3: 0.05}

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Approximate token count: ~4 chars per token.

        Returns at least 1 for non-empty text, 0 for empty.
        """
        if not text:
            return 0
        return max(1, len(text) // 4)

    @staticmethod
    def split_sentences(text: str) -> list[str]:
        """Split text by sentence boundaries.

        Splits on '. ', '! ', '? ' and newlines.
        Preserves the delimiter at the end of each sentence.
        Returns empty list for empty/whitespace-only text.
        """
        if not text or not text.strip():
            return []

        # Split on sentence-ending punctuation followed by space/newline, or on newlines
        parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
        return [p.strip() for p in parts if p.strip()]

    @staticmethod
    def extract_summary(content: str, ratio: float) -> str:
        """Extractive summary: keep first `ratio` fraction of sentences.

        Always returns at least 1 sentence if content is non-empty.
        Returns empty string for empty content.
        """
        if not content or not content.strip():
            return ""

        sentences = HierarchicalSummarizer.split_sentences(content)
        if not sentences:
            return content.strip()

        keep = max(1, math.ceil(len(sentences) * ratio))
        return " ".join(sentences[:keep])

    @staticmethod
    def build_extractive_hierarchy(content: str) -> dict[int, str]:
        """Build 4-level hierarchy using extractive summarization.

        Returns {0: original, 1: ~40%, 2: ~15%, 3: ~5%}.
        Level 0 is always the original text.
        Higher levels are progressively more compressed.
        """
        result: dict[int, str] = {}
        for level, ratio in HierarchicalSummarizer.LEVEL_RATIOS.items():
            if level == 0:
                result[level] = content
            else:
                result[level] = HierarchicalSummarizer.extract_summary(content, ratio)
        return result

    @staticmethod
    def select_level(level_token_counts: dict[int, int], max_tokens: int) -> int:
        """Find deepest (most detailed) level that fits within max_tokens.

        Deepest = lowest level number (0 is most detailed).
        If nothing fits, return highest level (3 = most compressed).
        """
        # Try from most detailed (0) to most compressed (3)
        for level in range(HierarchicalSummarizer.NUM_LEVELS):
            count = level_token_counts.get(level, 0)
            if count <= max_tokens:
                return level
        return HierarchicalSummarizer.NUM_LEVELS - 1

    @staticmethod
    def estimate_depth(max_tokens: int, total_entry_tokens: int) -> int:
        """Estimate appropriate level based on budget ratio.

        High budget relative to entry size -> level 0 (full detail).
        Low budget -> level 3 (most compressed).

        Uses LEVEL_RATIOS thresholds:
          ratio >= 1.0  -> level 0
          ratio >= 0.40 -> level 1
          ratio >= 0.15 -> level 2
          otherwise     -> level 3
        """
        if total_entry_tokens <= 0:
            return 0

        ratio = max_tokens / total_entry_tokens

        # Walk from most detailed to most compressed
        for level in range(HierarchicalSummarizer.NUM_LEVELS):
            if ratio >= HierarchicalSummarizer.LEVEL_RATIOS[level]:
                return level

        return HierarchicalSummarizer.NUM_LEVELS - 1

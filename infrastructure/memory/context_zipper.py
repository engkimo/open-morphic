"""ContextZipper — query-adaptive context compression.

Compresses conversation history to fit within a token budget, prioritizing
messages that are most relevant to the current query and most recent.

Pure utility — no external dependencies, no ports needed.
"""

from __future__ import annotations


def _estimate_tokens(text: str) -> int:
    """Approximate token count: ~4 chars per token."""
    return max(1, len(text) // 4)


def _keyword_overlap(text: str, query: str) -> float:
    """Score text by keyword overlap with query (0.0-1.0)."""
    query_words = set(query.lower().split())
    if not query_words:
        return 0.0
    text_words = set(text.lower().split())
    overlap = len(query_words & text_words)
    return overlap / len(query_words)


class ContextZipper:
    """Compress conversation history to fit within a token budget.

    Strategy:
    1. Score each message: recency_weight + keyword_overlap(msg, query)
    2. Sort by score descending
    3. Greedily include messages until max_tokens exhausted
    4. Return concatenated result

    Token estimation: len(text) // 4 (approx 4 chars per token).
    """

    def compress(
        self,
        history: list[str],
        query: str,
        max_tokens: int = 500,
    ) -> str:
        """Compress history into a string fitting within max_tokens.

        Args:
            history: List of conversation messages (oldest first).
            query: Current query — used for relevance scoring.
            max_tokens: Target token budget.

        Returns:
            Compressed context string.
        """
        if not history:
            return ""

        total_count = len(history)
        scored: list[tuple[float, int, str]] = []

        for idx, msg in enumerate(history):
            recency = (idx + 1) / total_count  # 0→1, recent = higher
            relevance = _keyword_overlap(msg, query)
            score = recency * 0.4 + relevance * 0.6
            scored.append((score, idx, msg))

        scored.sort(key=lambda x: x[0], reverse=True)

        budget = max_tokens
        selected: list[tuple[int, str]] = []

        for _score, idx, msg in scored:
            if budget <= 0:
                break
            tokens = _estimate_tokens(msg)
            # Account for newline separator between messages
            separator_cost = 1 if selected else 0
            if tokens + separator_cost <= budget:
                selected.append((idx, msg))
                budget -= tokens + separator_cost

        selected.sort(key=lambda x: x[0])
        return "\n".join(msg for _, msg in selected)

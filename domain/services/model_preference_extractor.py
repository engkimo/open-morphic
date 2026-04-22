"""ModelPreferenceExtractor — pure domain service to extract model names from goals.

No I/O, no external dependencies. Uses regex to detect model aliases in
natural-language goal text (English and Japanese).
"""

from __future__ import annotations

import re

from domain.value_objects.collaboration_mode import CollaborationMode
from domain.value_objects.model_preference import ModelPreference

# Canonical alias → LiteLLM model ID mapping
_MODEL_ALIASES: dict[str, str] = {
    "gpt": "o4-mini",
    "chatgpt": "o4-mini",
    "openai": "o4-mini",
    "codex": "o4-mini",
    "claude": "claude-sonnet-4-6",
    "anthropic": "claude-sonnet-4-6",
    "gemini": "gemini/gemini-3-pro-preview",
    "google": "gemini/gemini-3-pro-preview",
    "ollama": "ollama/qwen3:8b",
}

# Sorted longest-first so e.g. "chatgpt" matches before "gpt"
_ALIAS_KEYS = sorted(_MODEL_ALIASES.keys(), key=len, reverse=True)

# Pattern: ASCII-letter boundary (not \b which treats CJK as \w in Unicode mode)
_ALIAS_PATTERN = re.compile(
    r"(?i)(?<![a-zA-Z])(" + "|".join(re.escape(k) for k in _ALIAS_KEYS) + r")(?![a-zA-Z])"
)

# Collaboration mode detection — priority: COMPARISON > DIVERSE > PARALLEL > AUTO
_COLLAB_PATTERNS: list[tuple[CollaborationMode, re.Pattern[str]]] = [
    (
        CollaborationMode.COMPARISON,
        re.compile(r"比較|比べ|(?<![a-zA-Z])vs(?![a-zA-Z])|compare|versus", re.IGNORECASE),
    ),
    (
        CollaborationMode.DIVERSE,
        re.compile(
            r"それぞれ|各自?で|each\s+model|different\s+(?:aspect|angle)",
            re.IGNORECASE,
        ),
    ),
    (
        CollaborationMode.PARALLEL,
        re.compile(
            r"一緒に|同時に|並列|together|simultaneously|parallel",
            re.IGNORECASE,
        ),
    ),
]

# Japanese particles and connectors commonly surrounding model names
_JP_CLEANUP = re.compile(
    r"[、,]\s*|\s*[とやで]\s*(?=一緒|使って|を使|それぞれ|各|同時|並列|比較)"
    r"|\s*を?\s*(?:使って|使い|使う|を使って)"
    r"|\s*と\s*一緒に"
    r"|\s*(?:それぞれ|各自?|同時に|並列で|で)"
)


class ModelPreferenceExtractor:
    """Extract model preferences from goal text.

    Pure domain service — no I/O, fully deterministic.

    Example::

        pref = ModelPreferenceExtractor.extract(
            "gptとgemini,claudeと一緒に映画チケットを探して"
        )
        assert pref.models == ("o4-mini", "gemini/gemini-3-pro-preview", "claude-sonnet-4-6")
        assert "映画チケットを探して" in pref.clean_goal
    """

    @staticmethod
    def extract(goal: str) -> ModelPreference:
        """Extract model aliases from *goal* and return cleaned text.

        Returns ModelPreference with:
        - ``models``: de-duplicated tuple of LiteLLM model IDs (preserving
          first-occurrence order).
        - ``clean_goal``: goal with model names and surrounding connectors removed.
        """
        found_ids: list[str] = []
        seen: set[str] = set()

        for match in _ALIAS_PATTERN.finditer(goal):
            alias = match.group(1).lower()
            model_id = _MODEL_ALIASES[alias]
            if model_id not in seen:
                found_ids.append(model_id)
                seen.add(model_id)

        if not found_ids:
            return ModelPreference(models=(), clean_goal=goal)

        # Remove matched model aliases from text
        cleaned = _ALIAS_PATTERN.sub("", goal)
        # Remove Japanese connectors/particles left dangling
        cleaned = _JP_CLEANUP.sub(" ", cleaned)
        # Collapse whitespace and strip
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        # Remove leading/trailing commas or particles
        cleaned = re.sub(r"^[、,\s]+|[、,\s]+$", "", cleaned)
        # Remove orphaned leading particles left after model name removal
        # (e.g. "gptとclaudeで、..." → "とで、..." → "と ..." after cleanup)
        cleaned = re.sub(r"^[とやの]\s*", "", cleaned)

        collab = ModelPreferenceExtractor._detect_collaboration_mode(
            goal,
            len(found_ids),
        )

        return ModelPreference(
            models=tuple(found_ids),
            clean_goal=cleaned if cleaned else goal,
            collaboration_mode=collab,
        )

    @staticmethod
    def _detect_collaboration_mode(
        goal: str,
        model_count: int,
    ) -> CollaborationMode:
        """Detect collaboration mode from goal keywords.

        Only meaningful for multi-model (>=2). Single/zero always returns AUTO.
        Priority: COMPARISON > DIVERSE > PARALLEL > AUTO.
        """
        if model_count < 2:
            return CollaborationMode.AUTO
        for mode, pattern in _COLLAB_PATTERNS:
            if pattern.search(goal):
                return mode
        return CollaborationMode.AUTO

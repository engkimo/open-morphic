"""KVCacheOptimizer — Manus Principle 1: stable prefix for KV-cache hits.

The first ~128 tokens of the system prompt MUST be identical across calls.
Dynamic content (timestamps, session info) goes in a trailing section.
JSON serialization is deterministic (sort_keys=True).
"""

from __future__ import annotations

import json
from typing import Any

# Stable prefix — NEVER modify this string. KV-cache depends on it.
_STABLE_PREFIX = (
    "You are Morphic-Agent, a self-evolving AI agent framework. "
    "You decompose complex goals into subtasks, execute them via "
    "a DAG-based task graph, and learn from failures to improve. "
    "Always respond with concrete, actionable results."
)


class KVCacheOptimizer:
    """Build system prompts with a stable prefix for KV-cache optimization.

    The stable prefix is immutable and always appears first.
    Dynamic context is appended after, so cache hits are maximized.
    """

    def __init__(self, stable_prefix: str | None = None) -> None:
        self._stable_prefix = stable_prefix or _STABLE_PREFIX

    @property
    def stable_prefix(self) -> str:
        return self._stable_prefix

    def build_system_prompt(self, dynamic_context: dict[str, Any] | None = None) -> str:
        """Build a system prompt: stable prefix + optional dynamic context.

        The prefix is always identical → KV-cache hit on the prefix portion.
        Dynamic context is appended after and serialized deterministically.
        """
        parts = [self._stable_prefix]

        if dynamic_context:
            serialized = self.serialize_context(dynamic_context)
            parts.append(f"\n\nCurrent context:\n{serialized}")

        return "".join(parts)

    @staticmethod
    def serialize_context(context: dict[str, Any]) -> str:
        """Deterministic JSON serialization — sort_keys=True, no ensure_ascii."""
        return json.dumps(context, sort_keys=True, ensure_ascii=False, indent=None)

    def validate_prefix_stability(self, prompt: str) -> bool:
        """Check that a prompt starts with the expected stable prefix."""
        return prompt.startswith(self._stable_prefix)

"""AnswerExtractor — strip LLM verbosity from responses.

Pure domain service: no I/O, no framework dependencies.
Strips <think> tags, preambles, and boilerplate to extract the core answer.
"""

from __future__ import annotations

import re

from domain.value_objects.task_complexity import TaskComplexity

# Preamble patterns to strip (case-insensitive)
_PREAMBLE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^(?:the\s+)?answer\s+is[:\s]*", re.IGNORECASE),
    re.compile(r"^(?:the\s+)?result\s+is[:\s]*", re.IGNORECASE),
    re.compile(r"^sure[!,.]?\s*(?:here(?:\s+(?:is|are))?[:\s]*)?", re.IGNORECASE),
    re.compile(r"^of\s+course[!,.]?\s*", re.IGNORECASE),
    re.compile(
        r"^here(?:'s|\s+is|\s+are)\s+(?:the\s+)?"
        r"(?:answer|result|solution)[:\s]*",
        re.IGNORECASE,
    ),
    re.compile(r"^certainly[!,.]?\s*", re.IGNORECASE),
    re.compile(r"^the\s+(?:answer|result|solution)\s*[:]\s*", re.IGNORECASE),
]

# Regex to strip <think>...</think> blocks (e.g. qwen3 reasoning)
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class AnswerExtractor:
    """Extract the core answer from LLM output, adapting to complexity."""

    @staticmethod
    def extract(response: str, complexity: TaskComplexity) -> str:
        """Extract clean answer from LLM response.

        For SIMPLE tasks: aggressively strip thinking tags and preambles.
        For MEDIUM/COMPLEX: only strip thinking tags but preserve structure.

        Args:
            response: Raw LLM output.
            complexity: Task complexity level.

        Returns:
            Cleaned response string.
        """
        if not response:
            return ""

        text = response

        # Always strip <think> tags
        text = _THINK_TAG_RE.sub("", text).strip()

        if complexity == TaskComplexity.SIMPLE:
            text = AnswerExtractor._strip_preambles(text)
            text = AnswerExtractor._strip_trailing_explanation(text)

        return text.strip()

    @staticmethod
    def _strip_preambles(text: str) -> str:
        """Remove common LLM preamble phrases, applying patterns iteratively."""
        result = text
        changed = True
        while changed:
            changed = False
            for pattern in _PREAMBLE_PATTERNS:
                new = pattern.sub("", result, count=1).strip()
                if new != result:
                    result = new
                    changed = True
                    break
        return result

    @staticmethod
    def _strip_trailing_explanation(text: str) -> str:
        """For SIMPLE tasks, keep only the first line if rest is explanation."""
        lines = text.split("\n")
        if len(lines) <= 1:
            return text

        first_line = lines[0].strip()
        # If first line is short and looks like a direct answer, keep only it
        if len(first_line) <= 100 and len(lines) > 2:
            # Check if line 2+ starts with explanation patterns
            rest = "\n".join(lines[1:]).strip()
            explanation_re = (
                r"^(?:this|because|note|explanation|where|here"
                r"|let me|to|in|the|when|for|so|as)\b"
            )
            if re.match(explanation_re, rest, re.IGNORECASE):
                return first_line

        return text

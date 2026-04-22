"""ArtifactExtractor — smart extraction of structured artifacts from engine output.

Sprint 13.4b: Artifact Runtime Extraction.
  - Parse raw text output from any engine (Claude Code, Gemini CLI, Codex, etc.)
  - Extract structured content: code blocks, URLs, JSON data
  - Match extracted content to artifact keys using keyword heuristics
  - Fall back to positional values for unmatched keys

This is a generic framework capability — no scenario-specific logic.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# ── Regex patterns ──
# Fenced code blocks: ```lang\n...\n```
_CODE_BLOCK_RE = re.compile(r"```(\w+)?\s*\n(.*?)```", re.DOTALL)

# URLs: http(s)://...
_URL_RE = re.compile(r"https?://[^\s)<>\"']+")

# JSON inside ```json fences
_JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)


# ── Key-matching keyword sets ──
# Generic categories for heuristic matching. NOT scenario-specific.

_CODE_KEYWORDS = frozenset(
    {
        "code",
        "implementation",
        "script",
        "program",
        "function",
        "class",
        "module",
        "snippet",
        "algorithm",
    }
)

_URL_KEYWORDS = frozenset(
    {
        "url",
        "urls",
        "link",
        "links",
        "href",
        "endpoint",
        "endpoints",
    }
)

_DATA_KEYWORDS = frozenset(
    {
        "data",
        "json",
        "payload",
        "schema",
        "config",
        "structured",
        "parsed",
        "result",
        "results",
    }
)


@dataclass(frozen=True)
class ExtractedContent:
    """Structured content extracted from raw text."""

    code_blocks: list[tuple[str, str]] = field(default_factory=list)  # (language, code)
    urls: list[str] = field(default_factory=list)
    json_blocks: list[str] = field(default_factory=list)
    full_text: str = ""


class ArtifactExtractor:
    """Extract structured artifacts from engine/LLM output text.

    Parses raw text to find code blocks, URLs, and JSON data,
    then matches extracted content to artifact keys using keyword heuristics.
    """

    @staticmethod
    def extract(text: str) -> ExtractedContent:
        """Parse raw text into structured content categories.

        Extracts:
          - Fenced code blocks (```lang ... ```)
          - URLs (http/https)
          - JSON blocks (```json ... ``` with valid JSON)

        Args:
            text: Raw text output from any engine or LLM.

        Returns:
            ExtractedContent with categorized content.
        """
        if not text:
            return ExtractedContent()

        # Code blocks
        code_blocks: list[tuple[str, str]] = []
        for match in _CODE_BLOCK_RE.finditer(text):
            lang = (match.group(1) or "").strip().lower()
            code = match.group(2).strip()
            if code:
                code_blocks.append((lang, code))

        # URLs (unique, order-preserved)
        urls = list(dict.fromkeys(_URL_RE.findall(text)))

        # JSON blocks (from ```json fences, validated)
        json_blocks: list[str] = []
        for match in _JSON_FENCE_RE.finditer(text):
            block = match.group(1).strip()
            if block:
                try:
                    json.loads(block)
                    json_blocks.append(block)
                except (json.JSONDecodeError, ValueError):
                    pass

        return ExtractedContent(
            code_blocks=code_blocks,
            urls=urls,
            json_blocks=json_blocks,
            full_text=text,
        )

    @staticmethod
    def match_to_keys(
        extracted: ExtractedContent,
        keys: list[str],
        fallback_values: list[str] | None = None,
    ) -> dict[str, str]:
        """Match extracted content to artifact keys using keyword heuristics.

        For each key, determines the best content type based on keyword analysis:
        - Keys containing code-related words -> first available code block
        - Keys containing URL-related words -> joined URLs
        - Keys containing data-related words -> first JSON block
        - Default -> positional fallback value, or full text

        Keyword matching is generic and not tied to any specific use case.
        When smart matching finds no content of the matched type,
        falls back to positional values (backwards compatible with Sprint 13.4a).

        Args:
            extracted: Structured content from extract().
            keys: Artifact key names to fill.
            fallback_values: Positional fallback values (e.g. [result, code, output]).

        Returns:
            Dict mapping each key to its matched content.
        """
        result: dict[str, str] = {}
        used_code_idx = 0

        for i, key in enumerate(keys):
            key_lower = key.lower().replace("-", "_").replace(" ", "_")
            key_words = set(key_lower.split("_"))

            code_score = len(key_words & _CODE_KEYWORDS)
            url_score = len(key_words & _URL_KEYWORDS)
            data_score = len(key_words & _DATA_KEYWORDS)

            max_score = max(code_score, url_score, data_score)
            matched = False

            if max_score > 0:
                # Try categories in priority order: code > url > data
                if (
                    code_score == max_score
                    and extracted.code_blocks
                    and used_code_idx < len(extracted.code_blocks)
                ):
                    _, code = extracted.code_blocks[used_code_idx]
                    result[key] = code
                    used_code_idx += 1
                    matched = True
                if not matched and url_score == max_score and extracted.urls:
                    result[key] = "\n".join(extracted.urls)
                    matched = True
                if not matched and data_score == max_score and extracted.json_blocks:
                    result[key] = extracted.json_blocks[0]
                    matched = True

            if not matched:
                # Positional fallback (backwards compatible with Sprint 13.4a)
                if fallback_values:
                    if i < len(fallback_values):
                        result[key] = fallback_values[i]
                    else:
                        result[key] = fallback_values[0]
                else:
                    result[key] = extracted.full_text

        return result

    @staticmethod
    def extract_and_match(
        text: str,
        keys: list[str],
        fallback_values: list[str] | None = None,
    ) -> dict[str, str]:
        """Convenience: extract structured content then match to keys.

        Args:
            text: Raw text output from engine/LLM.
            keys: Artifact key names to fill.
            fallback_values: Positional fallback values.

        Returns:
            Dict mapping each key to matched content.
        """
        extracted = ArtifactExtractor.extract(text)
        return ArtifactExtractor.match_to_keys(extracted, keys, fallback_values)

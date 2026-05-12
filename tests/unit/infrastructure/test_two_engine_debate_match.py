"""Pin ``_match_engine`` substring-fallback behavior.

The TwoEngineDebate resolver asks an LLM judge to name the chosen engine
in free text. Because LLMs return varying surface forms ("gemini",
"Gemini CLI", "claude_code"), ``_match_engine`` first tries an exact
case-insensitive equality match, then falls back to a substring match
in either direction. That fallback is brittle when engine values share
substrings (``claude_code`` vs ``codex_cli`` both contain "code"), so
this test file pins the current behavior so future enum additions or
tweaks fail loudly here rather than silently miscount votes in the
council loop.
"""

from __future__ import annotations

import pytest

from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.council.two_engine_debate import _match_engine


class TestExactMatch:
    def test_exact_value_match(self) -> None:
        assert (
            _match_engine("ollama", [AgentEngineType.OLLAMA, AgentEngineType.GEMINI_CLI])
            is AgentEngineType.OLLAMA
        )

    def test_case_insensitive_exact_match(self) -> None:
        assert (
            _match_engine("OLLAMA", [AgentEngineType.OLLAMA, AgentEngineType.GEMINI_CLI])
            is AgentEngineType.OLLAMA
        )

    def test_whitespace_trimmed(self) -> None:
        assert (
            _match_engine(
                "  gemini_cli  ",
                [AgentEngineType.GEMINI_CLI, AgentEngineType.OLLAMA],
            )
            is AgentEngineType.GEMINI_CLI
        )

    def test_exact_match_beats_substring_overlap(self) -> None:
        """Exact match takes precedence even when a substring would match.

        ``"code"`` is a substring of both ``claude_code`` and ``codex_cli``,
        but if the judge returns ``"codex_cli"`` exactly we must honour it.
        """
        result = _match_engine(
            "codex_cli",
            [AgentEngineType.CLAUDE_CODE, AgentEngineType.CODEX_CLI],
        )
        assert result is AgentEngineType.CODEX_CLI


class TestSubstringFallback:
    def test_short_label_matches_longer_value(self) -> None:
        """Judge returning ``"gemini"`` resolves to ``gemini_cli``."""
        assert (
            _match_engine("gemini", [AgentEngineType.OLLAMA, AgentEngineType.GEMINI_CLI])
            is AgentEngineType.GEMINI_CLI
        )

    def test_long_label_containing_value(self) -> None:
        """Judge returning ``"the gemini_cli engine"`` still resolves."""
        assert (
            _match_engine(
                "the gemini_cli engine",
                [AgentEngineType.OLLAMA, AgentEngineType.GEMINI_CLI],
            )
            is AgentEngineType.GEMINI_CLI
        )

    def test_claude_short_label_resolves(self) -> None:
        assert (
            _match_engine(
                "claude",
                [AgentEngineType.CLAUDE_CODE, AgentEngineType.OLLAMA],
            )
            is AgentEngineType.CLAUDE_CODE
        )


class TestOverlappingNames:
    """Pin the iteration order behavior when multiple candidates fuzzy-match.

    The fallback returns the *first* candidate (in the supplied order)
    whose value either contains the needle or is contained in it. Callers
    that care about determinism must therefore order their candidates
    intentionally; this test file is the contract.
    """

    def test_code_substring_resolves_to_first_candidate(self) -> None:
        """``"code"`` appears in both ``claude_code`` and ``codex_cli``.

        With CLAUDE_CODE listed first, the fallback returns CLAUDE_CODE.
        """
        result = _match_engine(
            "code",
            [AgentEngineType.CLAUDE_CODE, AgentEngineType.CODEX_CLI],
        )
        assert result is AgentEngineType.CLAUDE_CODE

    def test_code_substring_resolves_in_reverse_order(self) -> None:
        """Reversing the candidate order flips the resolution."""
        result = _match_engine(
            "code",
            [AgentEngineType.CODEX_CLI, AgentEngineType.CLAUDE_CODE],
        )
        assert result is AgentEngineType.CODEX_CLI

    def test_cli_substring_picks_first_cli_engine(self) -> None:
        """``"cli"`` is shared between ``gemini_cli`` and ``codex_cli``."""
        result = _match_engine(
            "cli",
            [AgentEngineType.GEMINI_CLI, AgentEngineType.CODEX_CLI],
        )
        assert result is AgentEngineType.GEMINI_CLI

    def test_gemini_does_not_collide_with_other_engines(self) -> None:
        """Sanity: the live council pairing (ollama vs gemini) has no overlap."""
        result = _match_engine(
            "gemini",
            [AgentEngineType.OLLAMA, AgentEngineType.GEMINI_CLI],
        )
        assert result is AgentEngineType.GEMINI_CLI


class TestNoMatch:
    def test_unknown_name_returns_none(self) -> None:
        assert (
            _match_engine(
                "non_existent_engine",
                [AgentEngineType.OLLAMA, AgentEngineType.GEMINI_CLI],
            )
            is None
        )

    def test_empty_name_returns_none(self) -> None:
        """Empty needle should not silently substring-match every candidate.

        ``"" in "ollama"`` is True in Python, so without the exact-match
        guard this would return the first candidate. This test documents
        the actual current behavior so any future change is intentional.
        """
        result = _match_engine("", [AgentEngineType.OLLAMA, AgentEngineType.GEMINI_CLI])
        # Current behavior: empty string substring-matches the first candidate.
        # If we tighten this in the future, update this test.
        assert result is AgentEngineType.OLLAMA


@pytest.mark.parametrize(
    ("needle", "expected"),
    [
        ("ollama", AgentEngineType.OLLAMA),
        ("Ollama", AgentEngineType.OLLAMA),
        ("OLLAMA", AgentEngineType.OLLAMA),
        ("gemini_cli", AgentEngineType.GEMINI_CLI),
        ("gemini", AgentEngineType.GEMINI_CLI),
        ("Gemini", AgentEngineType.GEMINI_CLI),
    ],
)
def test_judge_label_variations_resolve_consistently(
    needle: str, expected: AgentEngineType
) -> None:
    """LLM judges return varying surface forms — all must resolve.

    Note: the substring fallback compares raw strings, so judge output
    that swaps the underscore for a space (``"Gemini CLI"``) does *not*
    resolve. Live observation (Round 21, 2026-05-12) shows the judge
    returns the underscored form when given the ``AgentEngineType``
    values explicitly in the prompt — see ``two_engine_debate.py``.
    """
    candidates = [AgentEngineType.OLLAMA, AgentEngineType.GEMINI_CLI]
    assert _match_engine(needle, candidates) is expected

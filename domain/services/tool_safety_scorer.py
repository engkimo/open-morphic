"""ToolSafetyScorer — Pure domain service. Scores tool safety from metadata signals.

No infrastructure dependencies. Uses only domain entities and value objects.
"""

from __future__ import annotations

import re

from domain.entities.tool_candidate import ToolCandidate
from domain.value_objects.tool_safety import SafetyTier

# Publishers with known trust (official MCP server providers)
_TRUSTED_PUBLISHERS: set[str] = {
    "anthropic",
    "modelcontextprotocol",
    "google",
    "microsoft",
    "openai",
    "github",
    "aws",
    "hashicorp",
    "docker",
    "vercel",
    "supabase",
    "cloudflare",
}

# Package name patterns that indicate suspicious tools
_SUSPICIOUS_PATTERNS: list[str] = [
    r"hack",
    r"exploit",
    r"crack",
    r"inject",
    r"malware",
    r"keylog",
    r"trojan",
    r"backdoor",
    r"phish",
    r"ransomware",
]

# Transport protocols and their trust level
_TRANSPORT_TRUST: dict[str, float] = {
    "stdio": 0.8,
    "sse": 0.6,
    "streamable-http": 0.6,
    "http": 0.4,
    "websocket": 0.4,
}

# Download count thresholds for popularity bonus
_POPULARITY_THRESHOLDS: list[tuple[int, float]] = [
    (10_000, 0.15),
    (1_000, 0.10),
    (100, 0.05),
]


class ToolSafetyScorer:
    """Score tool safety from metadata signals.

    Pure domain logic — no I/O, no external dependencies.
    """

    def score(self, candidate: ToolCandidate) -> ToolCandidate:
        """Compute safety_score and safety_tier, returning updated candidate."""
        raw_score = self._compute_raw_score(candidate)
        tier = self._tier_from_score(raw_score)

        # Check for forced unsafe
        if self._is_suspicious(candidate):
            raw_score = 0.0
            tier = SafetyTier.UNSAFE

        candidate.safety_score = round(min(raw_score, 1.0), 2)
        candidate.safety_tier = tier
        return candidate

    def _compute_raw_score(self, candidate: ToolCandidate) -> float:
        """Aggregate scoring signals into 0.0-1.0 score."""
        score = 0.0

        # Publisher trust (0.0 - 0.40)
        score += self._publisher_score(candidate.publisher)

        # Transport trust (0.0 - 0.25)
        score += self._transport_score(candidate.transport)

        # Popularity bonus (0.0 - 0.15)
        score += self._popularity_score(candidate.download_count)

        # Metadata completeness (0.0 - 0.20)
        score += self._metadata_score(candidate)

        return score

    def _publisher_score(self, publisher: str) -> float:
        """Score based on publisher reputation."""
        normalized = publisher.lower().strip()
        if normalized in _TRUSTED_PUBLISHERS:
            return 0.40
        if normalized:
            return 0.15
        return 0.0

    def _transport_score(self, transport: str) -> float:
        """Score based on transport protocol trust level."""
        normalized = transport.lower().strip()
        trust = _TRANSPORT_TRUST.get(normalized, 0.3)
        return trust * 0.25

    def _popularity_score(self, download_count: int) -> float:
        """Score based on download count popularity."""
        for threshold, bonus in _POPULARITY_THRESHOLDS:
            if download_count >= threshold:
                return bonus
        return 0.0

    def _metadata_score(self, candidate: ToolCandidate) -> float:
        """Score based on metadata completeness."""
        score = 0.0
        if candidate.description:
            score += 0.08
        if candidate.source_url:
            score += 0.06
        if candidate.install_command:
            score += 0.06
        return score

    def _is_suspicious(self, candidate: ToolCandidate) -> bool:
        """Check if tool name or package contains suspicious patterns."""
        text = f"{candidate.name} {candidate.package_name} {candidate.description}"
        text_lower = text.lower()
        return any(re.search(p, text_lower) for p in _SUSPICIOUS_PATTERNS)

    def _tier_from_score(self, score: float) -> SafetyTier:
        """Map numeric score to safety tier."""
        if score >= 0.70:
            return SafetyTier.VERIFIED
        if score >= 0.40:
            return SafetyTier.COMMUNITY
        if score >= 0.15:
            return SafetyTier.EXPERIMENTAL
        return SafetyTier.UNSAFE

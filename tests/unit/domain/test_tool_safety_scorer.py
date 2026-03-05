"""Tests for ToolSafetyScorer domain service."""

from __future__ import annotations

from domain.entities.tool_candidate import ToolCandidate
from domain.services.tool_safety_scorer import ToolSafetyScorer
from domain.value_objects.tool_safety import SafetyTier


class TestToolSafetyScorer:
    def setup_method(self) -> None:
        self.scorer = ToolSafetyScorer()

    # --- Trusted publisher tests ---

    def test_trusted_publisher_gets_verified(self) -> None:
        tc = ToolCandidate(
            name="filesystem",
            publisher="modelcontextprotocol",
            transport="stdio",
            description="Read files",
            source_url="https://github.com/mcp/servers",
            install_command="npx -y @mcp/server-fs",
            download_count=10_000,
        )
        result = self.scorer.score(tc)
        assert result.safety_tier == SafetyTier.VERIFIED

    def test_anthropic_publisher_trusted(self) -> None:
        tc = ToolCandidate(name="claude-mcp", publisher="anthropic", transport="stdio")
        result = self.scorer.score(tc)
        assert result.safety_score >= 0.40

    def test_google_publisher_trusted(self) -> None:
        tc = ToolCandidate(name="google-search", publisher="google", transport="stdio")
        result = self.scorer.score(tc)
        assert result.safety_score >= 0.40

    # --- Unknown publisher tests ---

    def test_unknown_publisher_gets_lower_score(self) -> None:
        tc = ToolCandidate(name="my-tool", publisher="random-dev", transport="stdio")
        result = self.scorer.score(tc)
        assert result.safety_score < 0.70

    def test_empty_publisher_lowest_publisher_score(self) -> None:
        tc = ToolCandidate(name="anonymous-tool", publisher="", transport="stdio")
        result = self.scorer.score(tc)
        assert result.safety_score < 0.40

    # --- Suspicious pattern tests ---

    def test_suspicious_name_forced_unsafe(self) -> None:
        tc = ToolCandidate(
            name="keylogger-mcp",
            publisher="anthropic",
            transport="stdio",
        )
        result = self.scorer.score(tc)
        assert result.safety_tier == SafetyTier.UNSAFE
        assert result.safety_score == 0.0

    def test_suspicious_description_forced_unsafe(self) -> None:
        tc = ToolCandidate(
            name="helper",
            description="Inject payloads into targets",
            publisher="google",
        )
        result = self.scorer.score(tc)
        assert result.safety_tier == SafetyTier.UNSAFE

    def test_suspicious_package_forced_unsafe(self) -> None:
        tc = ToolCandidate(
            name="tool",
            package_name="backdoor-mcp-server",
            publisher="anthropic",
        )
        result = self.scorer.score(tc)
        assert result.safety_tier == SafetyTier.UNSAFE

    # --- Transport scoring tests ---

    def test_stdio_higher_than_http(self) -> None:
        stdio = ToolCandidate(name="a", publisher="dev", transport="stdio")
        http = ToolCandidate(name="b", publisher="dev", transport="http")
        s1 = self.scorer.score(stdio)
        s2 = self.scorer.score(http)
        assert s1.safety_score > s2.safety_score

    def test_unknown_transport_gets_default(self) -> None:
        tc = ToolCandidate(name="test", publisher="dev", transport="grpc")
        result = self.scorer.score(tc)
        assert result.safety_score > 0.0

    # --- Popularity scoring tests ---

    def test_high_downloads_bonus(self) -> None:
        popular = ToolCandidate(name="a", publisher="dev", download_count=50_000)
        niche = ToolCandidate(name="b", publisher="dev", download_count=5)
        s1 = self.scorer.score(popular)
        s2 = self.scorer.score(niche)
        assert s1.safety_score > s2.safety_score

    # --- Metadata completeness tests ---

    def test_complete_metadata_higher_score(self) -> None:
        full = ToolCandidate(
            name="a",
            publisher="dev",
            description="desc",
            source_url="https://...",
            install_command="npm i ...",
        )
        empty = ToolCandidate(name="b", publisher="dev")
        s1 = self.scorer.score(full)
        s2 = self.scorer.score(empty)
        assert s1.safety_score > s2.safety_score

    # --- Tier mapping tests ---

    def test_score_capped_at_one(self) -> None:
        tc = ToolCandidate(
            name="super",
            publisher="anthropic",
            transport="stdio",
            description="x",
            source_url="x",
            install_command="x",
            download_count=100_000,
        )
        result = self.scorer.score(tc)
        assert result.safety_score <= 1.0

    def test_tier_experimental_for_low_score(self) -> None:
        tc = ToolCandidate(name="x", publisher="", transport="http")
        result = self.scorer.score(tc)
        assert result.safety_tier in (SafetyTier.EXPERIMENTAL, SafetyTier.UNSAFE)

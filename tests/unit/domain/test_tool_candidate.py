"""Tests for ToolCandidate entity."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.entities.tool_candidate import ToolCandidate
from domain.value_objects.tool_safety import SafetyTier


class TestToolCandidate:
    def test_create_minimal(self) -> None:
        tc = ToolCandidate(name="filesystem")
        assert tc.name == "filesystem"
        assert tc.safety_tier == SafetyTier.EXPERIMENTAL
        assert tc.safety_score == 0.0
        assert tc.transport == "stdio"

    def test_create_full(self) -> None:
        tc = ToolCandidate(
            name="filesystem",
            description="Read and write files",
            publisher="modelcontextprotocol",
            package_name="@modelcontextprotocol/server-filesystem",
            transport="stdio",
            install_command="npx -y @modelcontextprotocol/server-filesystem",
            source_url="https://github.com/modelcontextprotocol/servers",
            download_count=5000,
            safety_tier=SafetyTier.VERIFIED,
            safety_score=0.85,
        )
        assert tc.publisher == "modelcontextprotocol"
        assert tc.download_count == 5000

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValidationError):
            ToolCandidate(name="")

    def test_rejects_negative_downloads(self) -> None:
        with pytest.raises(ValidationError):
            ToolCandidate(name="test", download_count=-1)

    def test_rejects_safety_score_above_one(self) -> None:
        with pytest.raises(ValidationError):
            ToolCandidate(name="test", safety_score=1.5)

    def test_rejects_safety_score_below_zero(self) -> None:
        with pytest.raises(ValidationError):
            ToolCandidate(name="test", safety_score=-0.1)

    def test_assignment_validation(self) -> None:
        tc = ToolCandidate(name="test")
        with pytest.raises(ValidationError):
            tc.name = ""

    def test_discovered_at_auto_populated(self) -> None:
        tc = ToolCandidate(name="test")
        assert tc.discovered_at is not None

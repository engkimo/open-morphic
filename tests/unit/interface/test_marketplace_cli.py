"""Tests for marketplace CLI commands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from typer.testing import CliRunner

from application.use_cases.install_tool import InstallByNameResult, InstallToolUseCase
from domain.entities.tool_candidate import ToolCandidate
from domain.ports.tool_installer import InstallResult
from domain.ports.tool_registry import ToolSearchResult
from domain.value_objects.tool_safety import SafetyTier
from interface.cli._utils import _set_container
from interface.cli.main import app

runner = CliRunner()


def _candidate(name: str = "filesystem") -> ToolCandidate:
    return ToolCandidate(
        name=name,
        publisher="modelcontextprotocol",
        safety_tier=SafetyTier.VERIFIED,
        safety_score=0.85,
    )


@pytest.fixture(autouse=True)
def mock_container() -> MagicMock:
    container = MagicMock()
    uc = MagicMock(spec=InstallToolUseCase)
    uc.search = AsyncMock()
    uc.install_by_name = AsyncMock()
    uc.uninstall = AsyncMock()
    uc.list_installed = MagicMock(return_value=[])
    container.install_tool = uc
    _set_container(container)
    return container


class TestMarketplaceCLI:
    def test_search(self, mock_container: MagicMock) -> None:
        mock_container.install_tool.search.return_value = ToolSearchResult(
            query="fs", candidates=[_candidate()], total_count=1
        )
        result = runner.invoke(app, ["marketplace", "search", "fs"])
        assert result.exit_code == 0
        assert "filesystem" in result.output

    def test_search_no_results(self, mock_container: MagicMock) -> None:
        mock_container.install_tool.search.return_value = ToolSearchResult(
            query="x", candidates=[], total_count=0
        )
        result = runner.invoke(app, ["marketplace", "search", "x"])
        assert result.exit_code == 0
        assert "No tools found" in result.output

    def test_install_success(self, mock_container: MagicMock) -> None:
        mock_container.install_tool.install_by_name.return_value = InstallByNameResult(
            search_result=ToolSearchResult(query="fs", candidates=[_candidate()], total_count=1),
            install_result=InstallResult(tool_name="filesystem", success=True),
        )
        result = runner.invoke(app, ["marketplace", "install", "filesystem"])
        assert result.exit_code == 0
        assert "Installed" in result.output

    def test_install_not_found(self, mock_container: MagicMock) -> None:
        mock_container.install_tool.install_by_name.return_value = InstallByNameResult(
            search_result=ToolSearchResult(query="x", candidates=[], total_count=0),
            install_result=None,
        )
        result = runner.invoke(app, ["marketplace", "install", "nonexistent"])
        assert result.exit_code == 1

    def test_list_empty(self, mock_container: MagicMock) -> None:
        result = runner.invoke(app, ["marketplace", "list"])
        assert result.exit_code == 0
        assert "No tools found" in result.output

    def test_uninstall_success(self, mock_container: MagicMock) -> None:
        mock_container.install_tool.uninstall.return_value = InstallResult(
            tool_name="filesystem", success=True
        )
        result = runner.invoke(app, ["marketplace", "uninstall", "filesystem"])
        assert result.exit_code == 0
        assert "Uninstalled" in result.output

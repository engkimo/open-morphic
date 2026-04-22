"""Tests for InstallToolUseCase."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from application.use_cases.install_tool import InstallToolUseCase
from domain.entities.tool_candidate import ToolCandidate
from domain.ports.tool_installer import InstallResult
from domain.ports.tool_registry import ToolSearchResult
from domain.value_objects.tool_safety import SafetyTier


def _candidate(name: str = "filesystem") -> ToolCandidate:
    return ToolCandidate(
        name=name,
        publisher="modelcontextprotocol",
        safety_tier=SafetyTier.VERIFIED,
        safety_score=0.85,
    )


@pytest.fixture
def registry() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def installer() -> AsyncMock:
    mock = AsyncMock()
    mock.list_installed = MagicMock(return_value=[])
    mock.is_installed = MagicMock(return_value=False)
    return mock


@pytest.fixture
def use_case(registry: AsyncMock, installer: AsyncMock) -> InstallToolUseCase:
    return InstallToolUseCase(registry=registry, installer=installer)


class TestInstallToolUseCase:
    async def test_search(self, use_case: InstallToolUseCase, registry: AsyncMock) -> None:
        registry.search.return_value = ToolSearchResult(
            query="fs", candidates=[_candidate()], total_count=1
        )
        result = await use_case.search("fs")
        assert result.total_count == 1
        registry.search.assert_awaited_once_with("fs", limit=10)

    async def test_install(self, use_case: InstallToolUseCase, installer: AsyncMock) -> None:
        c = _candidate()
        installer.install.return_value = InstallResult(tool_name="filesystem", success=True)
        result = await use_case.install(c)
        assert result.success is True
        installer.install.assert_awaited_once_with(c)

    async def test_install_by_name_success(
        self, use_case: InstallToolUseCase, registry: AsyncMock, installer: AsyncMock
    ) -> None:
        c = _candidate()
        registry.search.return_value = ToolSearchResult(
            query="filesystem", candidates=[c], total_count=1
        )
        installer.install.return_value = InstallResult(tool_name="filesystem", success=True)
        result = await use_case.install_by_name("filesystem")
        assert result.install_result is not None
        assert result.install_result.success is True

    async def test_install_by_name_no_results(
        self, use_case: InstallToolUseCase, registry: AsyncMock
    ) -> None:
        registry.search.return_value = ToolSearchResult(
            query="nonexistent", candidates=[], total_count=0
        )
        result = await use_case.install_by_name("nonexistent")
        assert result.install_result is None

    async def test_install_by_name_picks_first(
        self, use_case: InstallToolUseCase, registry: AsyncMock, installer: AsyncMock
    ) -> None:
        c1 = _candidate("best")
        c2 = _candidate("second")
        registry.search.return_value = ToolSearchResult(
            query="test", candidates=[c1, c2], total_count=2
        )
        installer.install.return_value = InstallResult(tool_name="best", success=True)
        result = await use_case.install_by_name("test")
        installer.install.assert_awaited_once_with(c1)
        assert result.install_result is not None
        assert result.install_result.tool_name == "best"

    async def test_uninstall(self, use_case: InstallToolUseCase, installer: AsyncMock) -> None:
        installer.uninstall.return_value = InstallResult(tool_name="x", success=True)
        result = await use_case.uninstall("x")
        assert result.success is True

    def test_list_installed(self, use_case: InstallToolUseCase, installer: AsyncMock) -> None:
        c = _candidate()
        installer.list_installed.return_value = [c]
        result = use_case.list_installed()
        assert len(result) == 1

    async def test_search_with_custom_limit(
        self, use_case: InstallToolUseCase, registry: AsyncMock
    ) -> None:
        registry.search.return_value = ToolSearchResult(query="x", total_count=0)
        await use_case.search("x", limit=3)
        registry.search.assert_awaited_once_with("x", limit=3)

    async def test_install_by_name_propagates_search_error(
        self, use_case: InstallToolUseCase, registry: AsyncMock
    ) -> None:
        registry.search.return_value = ToolSearchResult(
            query="test", candidates=[], total_count=0, error="HTTP 500"
        )
        result = await use_case.install_by_name("test")
        assert result.search_result.error == "HTTP 500"
        assert result.install_result is None

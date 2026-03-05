"""Tests for MCPToolInstaller."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from domain.entities.tool_candidate import ToolCandidate
from domain.value_objects.tool_safety import SafetyTier
from infrastructure.marketplace.tool_installer import MCPToolInstaller


def _candidate(
    name: str = "test-tool",
    tier: SafetyTier = SafetyTier.COMMUNITY,
    install_command: str = "npm install test-tool",
) -> ToolCandidate:
    return ToolCandidate(
        name=name,
        safety_tier=tier,
        safety_score=0.5,
        install_command=install_command,
    )


@pytest.fixture
def installer() -> MCPToolInstaller:
    return MCPToolInstaller(safety_threshold=SafetyTier.EXPERIMENTAL)


class TestMCPToolInstaller:
    async def test_install_success(self, installer: MCPToolInstaller) -> None:
        candidate = _candidate()
        with patch("infrastructure.marketplace.tool_installer.asyncio") as mock_asyncio:
            proc = AsyncMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"ok", b""))
            mock_asyncio.create_subprocess_exec = AsyncMock(return_value=proc)
            mock_asyncio.wait_for = AsyncMock(return_value=(b"ok", b""))
            # Simpler: patch _run_install
            with patch.object(installer, "_run_install") as mock_run:
                from domain.ports.tool_installer import InstallResult

                mock_run.return_value = InstallResult(
                    tool_name="test-tool", success=True, message="installed"
                )
                result = await installer.install(candidate)

        assert result.success is True
        assert installer.is_installed("test-tool")

    async def test_install_blocks_unsafe(self, installer: MCPToolInstaller) -> None:
        candidate = _candidate(tier=SafetyTier.UNSAFE)
        result = await installer.install(candidate)
        assert result.success is False
        assert "Blocked" in (result.error or "")

    async def test_install_already_installed(self, installer: MCPToolInstaller) -> None:
        candidate = _candidate()
        installer._installed["test-tool"] = candidate
        result = await installer.install(candidate)
        assert result.success is True
        assert result.message == "Already installed"

    async def test_install_no_command(self, installer: MCPToolInstaller) -> None:
        candidate = _candidate(install_command="")
        result = await installer.install(candidate)
        assert result.success is False
        assert "No install command" in (result.error or "")

    async def test_uninstall_success(self, installer: MCPToolInstaller) -> None:
        candidate = _candidate()
        installer._installed["test-tool"] = candidate
        result = await installer.uninstall("test-tool")
        assert result.success is True
        assert not installer.is_installed("test-tool")

    async def test_uninstall_not_installed(self, installer: MCPToolInstaller) -> None:
        result = await installer.uninstall("nonexistent")
        assert result.success is False

    def test_list_installed_empty(self, installer: MCPToolInstaller) -> None:
        assert installer.list_installed() == []

    def test_list_installed_with_tools(self, installer: MCPToolInstaller) -> None:
        c1 = _candidate(name="tool-a")
        c2 = _candidate(name="tool-b")
        installer._installed["tool-a"] = c1
        installer._installed["tool-b"] = c2
        assert len(installer.list_installed()) == 2

    def test_is_installed(self, installer: MCPToolInstaller) -> None:
        installer._installed["x"] = _candidate(name="x")
        assert installer.is_installed("x") is True
        assert installer.is_installed("y") is False

    async def test_install_subprocess_failure(self, installer: MCPToolInstaller) -> None:
        candidate = _candidate()
        with patch.object(installer, "_run_install") as mock_run:
            from domain.ports.tool_installer import InstallResult

            mock_run.return_value = InstallResult(
                tool_name="test-tool", success=False, error="npm ERR!"
            )
            result = await installer.install(candidate)
        assert result.success is False
        assert not installer.is_installed("test-tool")

    async def test_custom_safety_threshold(self) -> None:
        strict = MCPToolInstaller(safety_threshold=SafetyTier.VERIFIED)
        candidate = _candidate(tier=SafetyTier.COMMUNITY)
        result = await strict.install(candidate)
        assert result.success is False
        assert "Blocked" in (result.error or "")

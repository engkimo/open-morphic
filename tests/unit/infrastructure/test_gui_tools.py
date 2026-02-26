"""Tests for GUI tools — Sprint 2-E. Mocked osascript, no real macOS calls."""

from __future__ import annotations

import platform
from unittest.mock import AsyncMock, patch

import pytest

from infrastructure.local_execution.tools import gui_tools


class TestGuiApplescript:
    @pytest.mark.asyncio
    async def test_applescript_runs_osascript(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"result", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            with patch("platform.system", return_value="Darwin"):
                result = await gui_tools.gui_applescript(
                    {"script": 'display dialog "Hello"'}
                )
        assert result == "result"
        mock_exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_applescript_empty_script_raises(self) -> None:
        with pytest.raises(ValueError, match="script is required"):
            await gui_tools.gui_applescript({})

    @pytest.mark.asyncio
    async def test_applescript_non_macos_raises(self) -> None:
        with patch("platform.system", return_value="Linux"):
            with pytest.raises(RuntimeError, match="macOS"):
                await gui_tools.gui_applescript({"script": "test"})

    @pytest.mark.asyncio
    async def test_applescript_failure(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"syntax error"))
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("platform.system", return_value="Darwin"):
                with pytest.raises(RuntimeError, match="AppleScript failed"):
                    await gui_tools.gui_applescript({"script": "bad script"})


class TestGuiOpenApp:
    @pytest.mark.asyncio
    async def test_open_app(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("platform.system", return_value="Darwin"):
                result = await gui_tools.gui_open_app({"app_name": "Safari"})
        assert "Safari" in result

    @pytest.mark.asyncio
    async def test_open_app_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="app_name is required"):
            await gui_tools.gui_open_app({})


class TestGuiScreenshotOcr:
    @pytest.mark.asyncio
    async def test_screenshot_captured(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("platform.system", return_value="Darwin"):
                result = await gui_tools.gui_screenshot_ocr({"path": "/tmp/shot.png"})
        assert "/tmp/shot.png" in result


class TestToolRegistration:
    def test_gui_tools_in_registry(self) -> None:
        from infrastructure.local_execution.tools import TOOL_REGISTRY

        gui_tools_names = [
            "gui_applescript", "gui_open_app",
            "gui_screenshot_ocr", "gui_accessibility",
        ]
        for name in gui_tools_names:
            assert name in TOOL_REGISTRY, f"{name} not in TOOL_REGISTRY"

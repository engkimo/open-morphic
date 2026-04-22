"""GUI tools — macOS AppleScript automation for LAEE."""

from __future__ import annotations

import asyncio
import platform
from typing import Any


async def gui_applescript(args: dict[str, Any]) -> str:
    """Execute an AppleScript command via osascript."""
    script = args.get("script", "")
    if not script:
        raise ValueError("script is required")
    if platform.system() != "Darwin":
        raise RuntimeError("AppleScript is only available on macOS")

    proc = await asyncio.create_subprocess_exec(
        "osascript",
        "-e",
        script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"AppleScript failed: {stderr.decode().strip()}")
    return stdout.decode().strip()


async def gui_open_app(args: dict[str, Any]) -> str:
    """Open an application by name."""
    app_name = args.get("app_name", "")
    if not app_name:
        raise ValueError("app_name is required")
    if platform.system() != "Darwin":
        raise RuntimeError("gui_open_app is only available on macOS")

    proc = await asyncio.create_subprocess_exec(
        "open",
        "-a",
        app_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to open {app_name}: {stderr.decode().strip()}")
    return f"Opened application: {app_name}"


async def gui_screenshot_ocr(args: dict[str, Any]) -> str:
    """Capture screen and perform basic OCR (macOS screencapture)."""
    path = args.get("path", "/tmp/morphic_screenshot.png")
    if platform.system() != "Darwin":
        raise RuntimeError("gui_screenshot_ocr is only available on macOS")

    proc = await asyncio.create_subprocess_exec(
        "screencapture",
        "-x",
        path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Screenshot failed: {stderr.decode().strip()}")
    return f"Screenshot captured to {path}"


async def gui_accessibility(args: dict[str, Any]) -> str:
    """Use Accessibility API via AppleScript System Events."""
    action = args.get("action", "")
    target = args.get("target", "")
    if not action or not target:
        raise ValueError("action and target are required")
    if platform.system() != "Darwin":
        raise RuntimeError("gui_accessibility is only available on macOS")

    script = f'tell application "System Events" to {action} {target}'
    return await gui_applescript({"script": script})

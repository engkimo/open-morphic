"""System tools — process, resource, clipboard, notifications for LAEE."""

from __future__ import annotations

import platform
import subprocess
from typing import Any

import psutil


async def system_process_list(args: dict[str, Any]) -> str:
    """List running processes (top 50 by CPU)."""
    procs: list[str] = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            procs.append(
                f"{info['pid']:>6} {info['name']:<30} "
                f"CPU:{info['cpu_percent']:>5.1f}% MEM:{info['memory_percent']:>5.1f}%"
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return "\n".join(procs[:50])


async def system_process_kill(args: dict[str, Any]) -> str:
    """Send signal to a process."""
    pid = int(args["pid"])
    sig = args.get("signal", 15)
    proc = psutil.Process(pid)
    proc.send_signal(sig)
    return f"Sent signal {sig} to PID {pid}"


async def system_resource_info(args: dict[str, Any]) -> str:
    """CPU, memory, disk usage summary."""
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return (
        f"CPU: {cpu}%\n"
        f"Memory: {mem.percent}% ({mem.used // 2**30}GB / {mem.total // 2**30}GB)\n"
        f"Disk: {disk.percent}% ({disk.used // 2**30}GB / {disk.total // 2**30}GB)\n"
        f"Platform: {platform.system()} {platform.release()}"
    )


async def system_clipboard_get(args: dict[str, Any]) -> str:
    """Read clipboard contents (macOS: pbpaste)."""
    result = subprocess.run(
        ["pbpaste"], capture_output=True, text=True, timeout=5, check=False
    )
    return result.stdout


async def system_clipboard_set(args: dict[str, Any]) -> str:
    """Write text to clipboard (macOS: pbcopy)."""
    text = args["text"]
    subprocess.run(["pbcopy"], input=text, text=True, timeout=5, check=False)
    return f"Copied {len(text)} chars to clipboard"


async def system_notify(args: dict[str, Any]) -> str:
    """Send desktop notification (macOS: osascript)."""
    title = args.get("title", "Morphic-Agent")
    message = args["message"]
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], timeout=5, check=False)
    return f"Notification sent: {title}"


async def system_screenshot(args: dict[str, Any]) -> str:
    """Capture screenshot (macOS: screencapture)."""
    path = args.get("path", "/tmp/morphic_screenshot.png")
    subprocess.run(["screencapture", "-x", path], timeout=10, check=False)
    return f"Screenshot saved to {path}"

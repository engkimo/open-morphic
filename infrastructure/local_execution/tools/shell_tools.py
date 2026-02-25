"""Shell tools — async subprocess wrappers for LAEE."""

from __future__ import annotations

import asyncio
from typing import Any


async def shell_exec(args: dict[str, Any]) -> str:
    """Execute a shell command, return stdout."""
    cmd = args.get("cmd", "")
    timeout = args.get("timeout", 30)
    cwd = args.get("cwd")

    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError as err:
        proc.kill()
        await proc.communicate()
        raise TimeoutError(f"Command timed out after {timeout}s: {cmd}") from err

    if proc.returncode != 0:
        err = stderr.decode().strip()
        raise RuntimeError(f"Command failed (exit {proc.returncode}): {err}")
    return stdout.decode().strip()


async def shell_background(args: dict[str, Any]) -> str:
    """Start a background process, return PID."""
    cmd = args.get("cmd", "")
    cwd = args.get("cwd")

    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        cwd=cwd,
    )
    return f"Background process started: PID {proc.pid}"


async def shell_stream(args: dict[str, Any]) -> str:
    """Execute command, capture stdout+stderr merged."""
    cmd = args.get("cmd", "")
    timeout = args.get("timeout", 30)
    cwd = args.get("cwd")

    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=cwd,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError as err:
        proc.kill()
        await proc.communicate()
        raise TimeoutError(f"Command timed out after {timeout}s: {cmd}") from err
    return stdout.decode().strip()


async def shell_pipe(args: dict[str, Any]) -> str:
    """Execute piped commands. args['cmds'] is a list of shell commands."""
    cmds: list[str] = args.get("cmds", [])
    if not cmds:
        return ""
    pipe_cmd = " | ".join(cmds)
    return await shell_exec({"cmd": pipe_cmd, "timeout": args.get("timeout", 30)})

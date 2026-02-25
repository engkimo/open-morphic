"""Dev tools — git, docker, package management wrappers for LAEE."""

from __future__ import annotations

from typing import Any

from infrastructure.local_execution.tools.shell_tools import shell_exec

_PKG_COMMANDS: dict[str, str] = {
    "pip": "pip install",
    "uv": "uv add",
    "brew": "brew install",
    "npm": "npm install",
}


async def dev_git(args: dict[str, Any]) -> str:
    """Run a git command."""
    cmd = args.get("cmd", "")
    return await shell_exec({"cmd": f"git {cmd}", "cwd": args.get("cwd")})


async def dev_docker(args: dict[str, Any]) -> str:
    """Run a docker command."""
    cmd = args.get("cmd", "")
    return await shell_exec({"cmd": f"docker {cmd}", "cwd": args.get("cwd")})


async def dev_pkg_install(args: dict[str, Any]) -> str:
    """Install a package using the specified manager."""
    pkg = args.get("pkg", "")
    manager = args.get("manager", "pip")
    base_cmd = _PKG_COMMANDS.get(manager, "pip install")
    return await shell_exec({"cmd": f"{base_cmd} {pkg}"})


async def dev_env_setup(args: dict[str, Any]) -> str:
    """Run a sequence of setup commands."""
    steps: list[str] = args.get("steps", [])
    results: list[str] = []
    for step in steps:
        result = await shell_exec({"cmd": step, "cwd": args.get("cwd")})
        results.append(f"[OK] {step}: {result}")
    return "\n".join(results) if results else "(no steps)"

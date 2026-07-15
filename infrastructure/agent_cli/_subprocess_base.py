"""SubprocessMixin — shared async subprocess runner for CLI-based agent drivers.

Used by ClaudeCodeDriver, CodexCLIDriver, GeminiCLIDriver.
Provides _run_cli() and _check_cli_exists() as reusable helpers.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass
class CLIResult:
    """Raw result from a subprocess invocation."""

    stdout: str
    stderr: str
    returncode: int


class SubprocessMixin:
    """Mixin providing async subprocess execution for CLI agent drivers."""

    async def _run_cli(
        self,
        cmd: list[str],
        timeout: float = 300.0,
        env: dict[str, str] | None = None,
    ) -> CLIResult:
        """Run a CLI command asynchronously with timeout.

        Args:
            cmd: Command and arguments.
            timeout: Seconds before killing the process.
            env: Environment variables for the subprocess. ``None`` inherits
                 the parent process environment.

        On timeout: kills the process and returns CLIResult with returncode=-1.
        """
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            return CLIResult(
                stdout=stdout_bytes.decode(errors="replace"),
                stderr=stderr_bytes.decode(errors="replace"),
                returncode=proc.returncode or 0,
            )
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return CLIResult(
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                returncode=-1,
            )

    async def _run_cli_streaming(
        self,
        cmd: list[str],
        *,
        timeout: float = 300.0,
        on_stdout_line: Callable[[str], Awaitable[None]],
        env: dict[str, str] | None = None,
    ) -> CLIResult:
        """Run a CLI while delivering decoded stdout lines incrementally."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        assert proc.stdout is not None
        assert proc.stderr is not None

        async def read_stdout() -> str:
            chunks: list[str] = []
            while line := await proc.stdout.readline():
                decoded = line.decode(errors="replace")
                chunks.append(decoded)
                await on_stdout_line(decoded.rstrip("\r\n"))
            return "".join(chunks)

        async def read_stderr() -> str:
            return (await proc.stderr.read()).decode(errors="replace")

        try:
            stdout, stderr, _ = await asyncio.wait_for(
                asyncio.gather(read_stdout(), read_stderr(), proc.wait()),
                timeout=timeout,
            )
            return CLIResult(
                stdout=stdout,
                stderr=stderr,
                returncode=proc.returncode or 0,
            )
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return CLIResult(
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                returncode=-1,
            )
        except Exception:
            proc.kill()
            await proc.communicate()
            raise

    @staticmethod
    def _check_cli_exists(binary: str) -> bool:
        """Check if a CLI binary is available on PATH."""
        return shutil.which(binary) is not None

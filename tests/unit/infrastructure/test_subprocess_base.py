"""Tests for incremental subprocess output delivery."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import patch

import pytest

from infrastructure.agent_cli._subprocess_base import SubprocessMixin


class _BlockingReader:
    async def readline(self) -> bytes:
        await asyncio.Future()
        return b""

    async def read(self) -> bytes:
        await asyncio.Future()
        return b""


class _CancellableProcess:
    def __init__(self) -> None:
        self.stdout = _BlockingReader()
        self.stderr = _BlockingReader()
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False
        self._stopped = asyncio.Event()

    async def communicate(self):
        await self._stopped.wait()
        return b"", b""

    async def wait(self) -> int:
        await self._stopped.wait()
        return self.returncode or 0

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15
        self._stopped.set()

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self._stopped.set()


@pytest.mark.asyncio
async def test_run_cli_streaming_delivers_stdout_lines_and_collects_stderr() -> None:
    runner = SubprocessMixin()
    delivered: list[str] = []

    async def on_stdout_line(line: str) -> None:
        delivered.append(line)

    result = await runner._run_cli_streaming(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "print('first', flush=True); "
                "print('second', flush=True); "
                "print('warning', file=sys.stderr, flush=True)"
            ),
        ],
        timeout=5.0,
        on_stdout_line=on_stdout_line,
    )

    assert result.returncode == 0
    assert delivered == ["first", "second"]
    assert result.stdout == "first\nsecond\n"
    assert result.stderr == "warning\n"


@pytest.mark.asyncio
async def test_run_cli_streaming_terminates_process_and_propagates_cancellation() -> None:
    runner = SubprocessMixin()
    process = _CancellableProcess()

    async def ignore_line(line: str) -> None:
        del line

    with patch(
        "infrastructure.agent_cli._subprocess_base.asyncio.create_subprocess_exec",
        return_value=process,
    ):
        task = asyncio.create_task(
            runner._run_cli_streaming(
                ["codex", "exec"],
                on_stdout_line=ignore_line,
            )
        )
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert process.terminated is True
    assert process.killed is False

"""Tests for incremental subprocess output delivery."""

from __future__ import annotations

import sys

import pytest

from infrastructure.agent_cli._subprocess_base import SubprocessMixin


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

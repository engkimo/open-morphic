"""Morphic Chat CLI command wiring."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from domain.entities.chat_session import PermissionMode
from infrastructure.engines.static_engine_registry import StaticEngineRegistry
from interface.cli._utils import _run
from interface.cli.chat_repl import ChatRepl
from interface.cli.formatters import console

_CHAT_WORKSPACE_OPTION = typer.Option(
    None,
    "--workspace",
    help="Workspace root.",
)
_CODE_WORKSPACE_OPTION = typer.Option(
    None,
    "--workspace",
    help="Workspace root.",
)


def chat_cmd(
    resume: str | None = typer.Option(
        None,
        "--resume",
        help="Resume a session id or 'latest'.",
    ),
    doctor: bool = typer.Option(
        False,
        "--doctor",
        help="Print chat CLI diagnostics instead of starting the REPL.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON for diagnostics.",
    ),
    workspace: Path | None = _CHAT_WORKSPACE_OPTION,
) -> None:
    """Start the Morphic terminal chat REPL."""
    if doctor:
        payload = _run(_chat_doctor_payload())
        if json_output:
            console.print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            console.print(f"engines={len(payload['engines'])}")
        return

    _run(ChatRepl(workspace_root=workspace or Path.cwd()).run(resume=resume))


def code_cmd(
    goal: str = typer.Argument(..., help="One-shot coding goal."),
    workspace: Path | None = _CODE_WORKSPACE_OPTION,
) -> None:
    """Run one coding goal and persist the session ledger."""
    _run(ChatRepl(workspace_root=workspace or Path.cwd()).run_goal(goal=goal))


async def _chat_doctor_payload() -> dict[str, object]:
    engines = await StaticEngineRegistry().list_engines()
    return {
        "engines": [engine.model_dump(mode="json") for engine in engines],
        "permission_modes": [mode.value for mode in PermissionMode],
    }

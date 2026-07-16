"""morphic chat-control — inspect or cancel an opt-in active chat turn."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from interface.cli._utils import _run
from interface.cli.chat_control_transport import (
    discover_active_chat_sessions,
    send_chat_control_command,
)
from interface.cli.formatters import console

chat_control_app = typer.Typer()
_WORKSPACE_OPTION = typer.Option(None, "--workspace", help="Workspace root.")
_SESSION_OPTION = typer.Option(None, "--session", help="Morphic chat session id.")


@chat_control_app.command("status")
def status_cmd(
    session_id: str | None = _SESSION_OPTION,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    workspace: Path | None = _WORKSPACE_OPTION,
) -> None:
    """Report whether one opt-in chat session has an active turn."""
    _run_control_command(
        command="status",
        session_id=session_id,
        json_output=json_output,
        workspace_root=workspace or Path.cwd(),
    )


@chat_control_app.command("cancel")
def cancel_cmd(
    session_id: str | None = _SESSION_OPTION,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    workspace: Path | None = _WORKSPACE_OPTION,
) -> None:
    """Cancel one active turn without terminating its chat REPL."""
    payload = _run_control_command(
        command="cancel",
        session_id=session_id,
        json_output=json_output,
        workspace_root=workspace or Path.cwd(),
    )
    if payload.get("cancelled") is not True:
        raise typer.Exit(code=1)


def _run_control_command(
    *,
    command: str,
    session_id: str | None,
    json_output: bool,
    workspace_root: Path,
) -> dict[str, object]:
    try:
        resolved_session = session_id or _discover_single_session(workspace_root)
        payload = _run(
            send_chat_control_command(
                workspace_root=workspace_root,
                session_id=resolved_session,
                command=command,
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None

    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    elif command == "status":
        console.print(
            f"session={payload['session_id']} active_turn={str(payload['active_turn']).lower()}"
        )
    else:
        console.print(
            f"session={payload['session_id']} cancelled={str(payload['cancelled']).lower()}"
        )
    return payload


def _discover_single_session(workspace_root: Path) -> str:
    sessions = discover_active_chat_sessions(workspace_root=workspace_root)
    if not sessions:
        raise ValueError("no active chat control session; start chat with --control")
    if len(sessions) > 1:
        raise ValueError("multiple active chat control sessions; specify --session")
    return sessions[0]

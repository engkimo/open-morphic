"""morphic hooks — validate and run Morphic Chat hooks."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import typer

from application.use_cases.execute_chat_hook import ExecuteChatHookUseCase
from domain.entities.chat_session import ChatSession, PermissionMode
from domain.entities.hook import HookType
from infrastructure.chat.jsonl_session_store import JsonlChatSessionStore
from infrastructure.hooks.workspace_hook_registry import WorkspaceHookRegistry
from interface.cli._utils import _run
from interface.cli.chat_command import _chat_hook_execution_mode, _chat_hook_executor
from interface.cli.formatters import console

hooks_app = typer.Typer()
_WORKSPACE_OPTION = typer.Option(
    None,
    "--workspace",
    help="Workspace root.",
)


@hooks_app.command("run")
def run_hook(
    hook_type: str = typer.Argument(..., help="Hook type to run, e.g. pre_tool."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    workspace: Path | None = _WORKSPACE_OPTION,
) -> None:
    """Run hooks of one type through the configured hook executor."""
    try:
        parsed_hook_type = HookType(hook_type)
        payload = _run(
            _run_hook_payload(
                hook_type=parsed_hook_type,
                workspace_root=workspace or Path.cwd(),
            )
        )
    except ValueError as exc:
        message = str(exc)
        if "is not a valid HookType" in message:
            valid = ", ".join(item.value for item in HookType)
            message = f"Invalid hook type '{hook_type}'. Expected one of: {valid}"
        typer.echo(f"Error: {message}", err=True)
        raise typer.Exit(code=2) from None

    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        summary = payload["summary"]
        console.print(
            "hooks "
            f"type={payload['hook_type']} "
            f"mode={payload['hook_execution_mode']} "
            f"succeeded={summary['succeeded']} "
            f"failed={summary['failed']} "
            f"skipped={summary['skipped']}"
        )

    if payload["summary"]["failed"] > 0:
        raise typer.Exit(code=1)


async def _run_hook_payload(
    *,
    hook_type: HookType,
    workspace_root: Path,
) -> dict[str, object]:
    store = JsonlChatSessionStore(workspace_root=workspace_root)
    session = ChatSession.start(
        session_id=uuid.uuid4().hex[:12],
        goal=f"run {hook_type.value} hooks",
        permission_mode=PermissionMode.CONFIRM_DESTRUCTIVE,
    )
    hook_runner = ExecuteChatHookUseCase(
        session_store=store,
        hook_registry=WorkspaceHookRegistry(workspace_root),
        hook_executor=_chat_hook_executor(workspace_root=workspace_root),
    )
    result = await hook_runner.execute(session=session, hook_type=hook_type)
    hook_results = [
        {
            "exit_code": hook_result.exit_code,
            "request_id": hook_result.request_id,
            "stderr_summary": hook_result.stderr_summary,
            "stdout_summary": hook_result.stdout_summary,
            "success": hook_result.success,
        }
        for hook_result in result.hook_results
    ]
    completed_by_request_id = {
        event.payload["request_id"]: event
        for event in result.events
        if event.type.value == "hook_execution_completed"
    }
    for hook_result in hook_results:
        event = completed_by_request_id.get(hook_result["request_id"])
        if event is not None:
            hook_result["hook_name"] = event.payload["hook_name"]

    skipped = sum(1 for event in result.events if event.type.value == "hook_execution_skipped")
    failed = sum(1 for hook_result in result.hook_results if not hook_result.success)
    succeeded = sum(1 for hook_result in result.hook_results if hook_result.success)
    return {
        "diagnostics": [
            diagnostic.model_dump(mode="json") for diagnostic in result.diagnostics
        ],
        "events": [event.model_dump(mode="json") for event in result.events],
        "hook_execution_mode": _chat_hook_execution_mode(),
        "hook_type": hook_type.value,
        "results": hook_results,
        "session_id": result.session.id,
        "summary": {
            "failed": failed,
            "skipped": skipped,
            "succeeded": succeeded,
        },
    }

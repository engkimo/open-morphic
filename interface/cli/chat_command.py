"""Morphic Chat CLI command wiring."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import typer

from domain.entities.chat_session import PermissionMode
from domain.ports.council_runtime import CouncilRuntimePort
from domain.ports.engine_registry import EngineRegistryPort
from infrastructure.council.local_chat_council_runtime import LocalChatCouncilRuntime
from infrastructure.council.route_chat_council_runtime import RouteChatCouncilRuntime
from infrastructure.engines.route_engine_registry import RouteEngineRegistry
from infrastructure.engines.static_engine_registry import StaticEngineRegistry
from interface.cli._utils import _get_container, _run
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


@contextmanager
def _disabled_logging(enabled: bool) -> Iterator[None]:
    if not enabled:
        yield
        return

    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous)


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
        with _disabled_logging(json_output):
            engine_registry = _chat_engine_registry()
            payload = _run(_chat_doctor_payload(engine_registry=engine_registry))
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            console.print(f"engines={len(payload['engines'])}")
        return

    with _disabled_logging(True):
        engine_registry = _chat_engine_registry()
        council_runtime = _chat_council_runtime()
    _run(
        ChatRepl(
            workspace_root=workspace or Path.cwd(),
            council_runtime=council_runtime,
            engine_registry=engine_registry,
        ).run(resume=resume)
    )


def code_cmd(
    goal: str = typer.Argument(..., help="One-shot coding goal."),
    workspace: Path | None = _CODE_WORKSPACE_OPTION,
) -> None:
    """Run one coding goal and persist the session ledger."""
    with _disabled_logging(True):
        engine_registry = _chat_engine_registry()
        council_runtime = _chat_council_runtime()
    _run(
        ChatRepl(
            workspace_root=workspace or Path.cwd(),
            council_runtime=council_runtime,
            engine_registry=engine_registry,
        ).run_goal(goal=goal)
    )


def _chat_engine_registry() -> EngineRegistryPort:
    try:
        container = _get_container()
        route_to_engine = getattr(container, "route_to_engine", None)
        if route_to_engine is not None:
            return RouteEngineRegistry(route_to_engine)
    except Exception:
        return StaticEngineRegistry()
    return StaticEngineRegistry()


def _chat_council_runtime() -> CouncilRuntimePort:
    if os.getenv("MORPHIC_CHAT_ROUTE_COUNCIL") != "1":
        return LocalChatCouncilRuntime()
    try:
        container = _get_container()
        route_to_engine = getattr(container, "route_to_engine", None)
        if route_to_engine is not None:
            return RouteChatCouncilRuntime(route_to_engine)
    except Exception:
        return LocalChatCouncilRuntime()
    return LocalChatCouncilRuntime()


async def _chat_doctor_payload(
    engine_registry: EngineRegistryPort | None = None,
) -> dict[str, object]:
    registry = engine_registry or StaticEngineRegistry()
    engines = await registry.list_engines()
    return {
        "engines": [engine.model_dump(mode="json") for engine in engines],
        "permission_modes": [mode.value for mode in PermissionMode],
    }

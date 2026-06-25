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
from domain.entities.council_runtime import CouncilRole
from domain.ports.council_runtime import CouncilRuntimePort
from domain.ports.engine_registry import EngineRegistryPort
from domain.value_objects.agent_engine import AgentEngineType
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
_CHAT_ROUTE_COUNCIL_OPTION = typer.Option(
    False,
    "--route-council",
    help="Use route-backed engines for chat council roles.",
)
_CODE_ROUTE_COUNCIL_OPTION = typer.Option(
    False,
    "--route-council",
    help="Use route-backed engines for chat council roles.",
)
_PLANNER_ENGINE_OPTION = typer.Option(
    None,
    "--planner-engine",
    help="Preferred route engine for the planner role.",
)
_CRITIC_ENGINE_OPTION = typer.Option(
    None,
    "--critic-engine",
    help="Preferred route engine for the critic role.",
)
_LEADER_ENGINE_OPTION = typer.Option(
    None,
    "--leader-engine",
    help="Preferred route engine for the leader role.",
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
    route_council: bool = _CHAT_ROUTE_COUNCIL_OPTION,
    planner_engine: str | None = _PLANNER_ENGINE_OPTION,
    critic_engine: str | None = _CRITIC_ENGINE_OPTION,
    leader_engine: str | None = _LEADER_ENGINE_OPTION,
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
        council_runtime = _chat_council_runtime(
            route_council=route_council,
            planner_engine=planner_engine,
            critic_engine=critic_engine,
            leader_engine=leader_engine,
        )
    _run(
        ChatRepl(
            workspace_root=workspace or Path.cwd(),
            council_runtime=council_runtime,
            engine_registry=engine_registry,
        ).run(resume=resume)
    )


def code_cmd(
    goal: str = typer.Argument(..., help="One-shot coding goal."),
    route_council: bool = _CODE_ROUTE_COUNCIL_OPTION,
    planner_engine: str | None = _PLANNER_ENGINE_OPTION,
    critic_engine: str | None = _CRITIC_ENGINE_OPTION,
    leader_engine: str | None = _LEADER_ENGINE_OPTION,
    workspace: Path | None = _CODE_WORKSPACE_OPTION,
) -> None:
    """Run one coding goal and persist the session ledger."""
    with _disabled_logging(True):
        engine_registry = _chat_engine_registry()
        council_runtime = _chat_council_runtime(
            route_council=route_council,
            planner_engine=planner_engine,
            critic_engine=critic_engine,
            leader_engine=leader_engine,
        )
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


def _chat_council_runtime(
    *,
    route_council: bool = False,
    planner_engine: str | None = None,
    critic_engine: str | None = None,
    leader_engine: str | None = None,
) -> CouncilRuntimePort:
    if not route_council and os.getenv("MORPHIC_CHAT_ROUTE_COUNCIL") != "1":
        return LocalChatCouncilRuntime()
    try:
        container = _get_container()
        route_to_engine = getattr(container, "route_to_engine", None)
        if route_to_engine is not None:
            return RouteChatCouncilRuntime(
                route_to_engine,
                role_engines=_role_engine_preferences(
                    planner_engine=planner_engine,
                    critic_engine=critic_engine,
                    leader_engine=leader_engine,
                ),
            )
    except Exception:
        return LocalChatCouncilRuntime()
    return LocalChatCouncilRuntime()


def _role_engine_preferences(
    *,
    planner_engine: str | None,
    critic_engine: str | None,
    leader_engine: str | None,
) -> dict[CouncilRole, AgentEngineType]:
    preferences: dict[CouncilRole, AgentEngineType] = {}
    for role, engine_id in [
        (CouncilRole.PLANNER, planner_engine),
        (CouncilRole.CRITIC, critic_engine),
        (CouncilRole.LEADER, leader_engine),
    ]:
        if engine_id:
            preferences[role] = AgentEngineType(engine_id)
    return preferences


async def _chat_doctor_payload(
    engine_registry: EngineRegistryPort | None = None,
) -> dict[str, object]:
    registry = engine_registry or StaticEngineRegistry()
    engines = await registry.list_engines()
    return {
        "engines": [engine.model_dump(mode="json") for engine in engines],
        "permission_modes": [mode.value for mode in PermissionMode],
    }

"""Morphic-Agent CLI — terminal interface to the same use cases as the API.

Entry point: `morphic` command (registered in pyproject.toml [project.scripts]).
"""

from __future__ import annotations

import asyncio
import importlib.metadata
from typing import Any

import typer

from interface.cli.formatters import console

app = typer.Typer(
    name="morphic",
    help="Morphic-Agent — Self-Evolving AI Agent Framework",
    no_args_is_help=True,
)

# Lazy singleton — created once on first access
_container_instance: Any = None


def _get_container() -> Any:
    """Lazy-init the AppContainer singleton. Swappable for testing."""
    global _container_instance  # noqa: PLW0603
    if _container_instance is None:
        from interface.api.container import AppContainer

        _container_instance = AppContainer()
    return _container_instance


def _set_container(container: Any) -> None:
    """Override the container (for testing)."""
    global _container_instance  # noqa: PLW0603
    _container_instance = container


def _run(coro: Any) -> Any:
    """Thin wrapper to run an async coroutine from sync typer commands.

    Falls back to loop.run_until_complete() when called inside an existing
    event loop (e.g. pytest-asyncio tests).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already inside a loop — run directly on it
    return loop.run_until_complete(coro)


def _version_callback(value: bool) -> None:
    if value:
        version = importlib.metadata.version("morphic-agent")
        console.print(f"morphic-agent {version}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Morphic-Agent CLI — Mission Control for Intelligence."""


# Import and register sub-commands (deferred to avoid circular imports)
def _register_commands() -> None:
    from interface.cli.commands.cost import cost_app
    from interface.cli.commands.model import model_app
    from interface.cli.commands.plan import plan_app
    from interface.cli.commands.task import task_app

    app.add_typer(task_app, name="task", help="Create, list, show, and cancel tasks.")
    app.add_typer(plan_app, name="plan", help="Create, review, approve, and reject plans.")
    app.add_typer(model_app, name="model", help="Manage LLM models.")
    app.add_typer(cost_app, name="cost", help="View cost tracking and budget.")


_register_commands()

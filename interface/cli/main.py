"""Morphic-Agent CLI — terminal interface to the same use cases as the API.

Entry point: `morphic` command (registered in pyproject.toml [project.scripts]).
"""

from __future__ import annotations

import importlib.metadata

import typer

from interface.cli._utils import _get_container, _run, _set_container  # noqa: F401
from interface.cli.formatters import console
from shared.config import settings
from shared.logging import setup_logging

setup_logging(settings.log_level)

app = typer.Typer(
    name="morphic",
    help="Morphic-Agent — Self-Evolving AI Agent Framework",
    no_args_is_help=True,
)


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
    from interface.cli.commands.a2a import a2a_app
    from interface.cli.commands.benchmark import benchmark_app
    from interface.cli.commands.cognitive import cognitive_app
    from interface.cli.commands.context import context_app
    from interface.cli.commands.cost import cost_app
    from interface.cli.commands.doctor import doctor_app
    from interface.cli.commands.engine import engine_app
    from interface.cli.commands.evolution import evolution_app
    from interface.cli.commands.fallback import fallback_app
    from interface.cli.commands.learning import learning_app
    from interface.cli.commands.marketplace import marketplace_app
    from interface.cli.commands.mcp import mcp_app
    from interface.cli.commands.memory import memory_app
    from interface.cli.commands.model import model_app
    from interface.cli.commands.plan import plan_app
    from interface.cli.commands.serve import serve_app
    from interface.cli.commands.task import task_app

    app.add_typer(task_app, name="task", help="Create, list, show, and cancel tasks.")
    app.add_typer(plan_app, name="plan", help="Create, review, approve, and reject plans.")
    app.add_typer(model_app, name="model", help="Manage LLM models.")
    app.add_typer(cost_app, name="cost", help="View cost tracking and budget.")
    app.add_typer(mcp_app, name="mcp", help="Manage MCP server.")
    app.add_typer(engine_app, name="engine", help="Manage agent execution engines.")
    app.add_typer(
        fallback_app,
        name="fallback",
        help="Inspect execution history, failures, and engine routing stats.",
    )
    app.add_typer(
        learning_app,
        name="learning",
        help="Inspect fractal engine learning data — error patterns and successful paths.",
    )
    app.add_typer(marketplace_app, name="marketplace", help="Search, install, and manage tools.")
    app.add_typer(memory_app, name="memory", help="List, search, show, and manage memory entries.")
    app.add_typer(
        context_app,
        name="context",
        help="Export context for AI platforms (claude_code, chatgpt, cursor, gemini).",
    )
    app.add_typer(
        evolution_app,
        name="evolution",
        help="Self-evolution stats, strategy updates, and reports.",
    )
    app.add_typer(
        cognitive_app,
        name="cognitive",
        help="UCL shared task state, affinity, handoff, and insights.",
    )
    app.add_typer(
        benchmark_app,
        name="benchmark",
        help="Run UCL benchmarks (context continuity, dedup accuracy).",
    )
    app.add_typer(
        a2a_app,
        name="a2a",
        help="A2A agent-to-agent conversations, messaging, and registry.",
    )
    app.add_typer(doctor_app, name="doctor", help="System health diagnostics.")
    app.add_typer(serve_app, name="serve", help="Start the HTTP API server.")


_register_commands()

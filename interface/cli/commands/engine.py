"""Engine subcommands — list available engines and run tasks via engine routing."""

from __future__ import annotations

import typer

from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from interface.cli.formatters import console, print_engine_result, print_engine_table, print_error
from interface.cli.main import _get_container, _run

engine_app = typer.Typer()


@engine_app.command("list")
def list_engines() -> None:
    """List all agent execution engines with availability."""
    c = _get_container()
    engines = _run(c.route_to_engine.list_engines())
    print_engine_table(engines)


@engine_app.command("run")
def run(
    task: str = typer.Argument(..., help="Task prompt to execute."),
    engine: str = typer.Option(
        None, "--engine", "-e", help="Engine override (e.g. ollama, claude_code)."
    ),
    task_type: str = typer.Option("simple_qa", "--type", "-t", help="Task type for routing."),
    budget: float = typer.Option(1.0, "--budget", "-b", help="Budget in USD."),
    model: str = typer.Option(None, "--model", "-m", help="Model override."),
    timeout: float = typer.Option(300.0, "--timeout", help="Timeout in seconds."),
) -> None:
    """Route a task to the best available engine and execute it."""
    c = _get_container()

    # Validate engine override
    preferred: AgentEngineType | None = None
    if engine is not None:
        try:
            preferred = AgentEngineType(engine)
        except ValueError as exc:
            print_error(f"Unknown engine: {engine}")
            raise typer.Exit(code=1) from exc

    # Validate task type
    try:
        tt = TaskType(task_type)
    except ValueError as exc:
        print_error(f"Unknown task type: {task_type}")
        raise typer.Exit(code=1) from exc

    with console.status("[blue]Routing and executing...[/]"):
        try:
            result = _run(
                c.route_to_engine.execute(
                    task=task,
                    task_type=tt,
                    budget=budget,
                    preferred_engine=preferred,
                    model=model,
                    timeout_seconds=timeout,
                )
            )
        except Exception as exc:
            print_error(str(exc))
            raise typer.Exit(code=1) from exc

    print_engine_result(result)

"""Council subcommand — run a two-engine debate and let a judge decide.

Two candidate engines argue (capability / cost / risk / approach) over a goal
and a resolver model resolves the debate with an explicit rationale. The
resolver model is config-driven (``MORPHIC_COUNCIL_RESOLVER_MODEL``); the
candidate engines are chosen with ``--engines``.
"""

from __future__ import annotations

import typer

from domain.entities.council import SubtaskBrief
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from interface.cli._utils import _get_container, _run
from interface.cli.formatters import console, print_council_debate, print_error

council_app = typer.Typer()


@council_app.command("debate")
def debate(
    goal: str = typer.Argument(..., help="The goal/question the engines debate over."),
    engines: str = typer.Option(
        "ollama,claude_code",
        "--engines",
        "-e",
        help="Exactly two candidate engines, comma-separated (e.g. ollama,claude_code).",
    ),
    task_type: str = typer.Option(
        "simple_qa", "--type", "-t", help="Task type hint for the brief."
    ),
) -> None:
    """Run a two-engine council debate over GOAL and print the judge's verdict.

    The resolver (judge) model comes from MORPHIC_COUNCIL_RESOLVER_MODEL.
    """
    names = [e.strip() for e in engines.split(",") if e.strip()]
    if len(names) != 2:
        print_error("--engines requires exactly two engines (e.g. ollama,claude_code).")
        raise typer.Exit(code=1)
    try:
        candidates = [AgentEngineType(n) for n in names]
    except ValueError:
        valid = ", ".join(e.value for e in AgentEngineType)
        print_error(f"Unknown engine in {names!r}. Valid: {valid}.")
        raise typer.Exit(code=1) from None
    try:
        tt = TaskType(task_type)
    except ValueError:
        valid = ", ".join(t.value for t in TaskType)
        print_error(f"Unknown task type {task_type!r}. Valid: {valid}.")
        raise typer.Exit(code=1) from None

    c = _get_container()
    subtask = SubtaskBrief(id="council-cli", description=goal, task_type=tt)

    console.print(f"\n[bold yellow]Council debate:[/] {goal}")
    console.print(f"[dim]candidates: {', '.join(names)}[/]\n")

    decision = _run(c.run_council_debate.execute(subtask, candidates))
    print_council_debate(decision, list(c.council_event_bus.events))

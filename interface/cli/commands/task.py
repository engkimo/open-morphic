"""Task subcommands — create, list, show, cancel."""

from __future__ import annotations

import typer

from interface.cli._utils import _get_container, _run
from interface.cli.formatters import console, print_error, print_task_detail, print_task_table

task_app = typer.Typer()


@task_app.command("create")
def create(
    goal: str = typer.Argument(..., help="Goal description for the task."),
    no_wait: bool = typer.Option(False, "--no-wait", help="Create without executing."),
) -> None:
    """Create a new task from a goal description."""
    c = _get_container()
    try:
        task = _run(c.create_task.execute(goal))
    except Exception as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc

    if no_wait:
        console.print(f"[green]Created:[/] {task.id}")
        return

    with console.status("[blue]Executing task...[/]"):
        try:
            task = _run(c.execute_task.execute(task.id))
        except Exception as exc:
            print_error(str(exc))
            raise typer.Exit(code=1) from exc

    print_task_detail(task)


@task_app.command("list")
def list_tasks() -> None:
    """List all tasks."""
    c = _get_container()
    tasks = _run(c.task_repo.list_all())
    print_task_table(tasks)


@task_app.command("show")
def show(
    task_id: str = typer.Argument(..., help="Task ID to show."),
) -> None:
    """Show details of a specific task."""
    c = _get_container()
    task = _run(c.task_repo.get_by_id(task_id))
    if task is None:
        print_error(f"Task {task_id} not found")
        raise typer.Exit(code=1)
    print_task_detail(task)


@task_app.command("cancel")
def cancel(
    task_id: str = typer.Argument(..., help="Task ID to cancel."),
) -> None:
    """Cancel a task by setting its status to FAILED."""
    from domain.value_objects.status import TaskStatus

    c = _get_container()
    task = _run(c.task_repo.get_by_id(task_id))
    if task is None:
        print_error(f"Task {task_id} not found")
        raise typer.Exit(code=1)
    task.status = TaskStatus.FAILED
    _run(c.task_repo.update(task))
    console.print(f"[yellow]Cancelled:[/] {task_id}")

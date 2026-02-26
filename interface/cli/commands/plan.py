"""Plan subcommands — create, list, show, approve, reject."""

from __future__ import annotations

import typer

from interface.cli.formatters import console, print_error
from interface.cli.main import _get_container, _run

plan_app = typer.Typer()


def _print_plan(plan) -> None:  # noqa: ANN001
    """Display a plan with cost table."""
    from rich.table import Table

    console.print(f"\n[bold]Plan:[/] {plan.goal}")
    console.print(f"ID: [dim]{plan.id}[/]")
    console.print(f"Status: [blue]{plan.status.value}[/]")

    if plan.steps:
        table = Table(title="Execution Steps")
        table.add_column("#", justify="right", style="dim")
        table.add_column("Description", min_width=30)
        table.add_column("Model")
        table.add_column("Est. Cost", justify="right")
        table.add_column("Est. Tokens", justify="right")

        for i, step in enumerate(plan.steps, 1):
            cost_str = (
                "[green]$0.0000[/]"
                if step.estimated_cost_usd == 0
                else f"${step.estimated_cost_usd:.4f}"
            )
            table.add_row(
                str(i),
                step.subtask_description[:60],
                step.proposed_model,
                cost_str,
                str(step.estimated_tokens),
            )
        console.print(table)

    total_style = "green" if plan.total_estimated_cost_usd == 0 else "yellow"
    console.print(
        f"\n[bold]Total estimated cost:[/] [{total_style}]${plan.total_estimated_cost_usd:.4f}[/]"
    )

    if plan.task_id:
        console.print(f"Task ID: [dim]{plan.task_id}[/]")


@plan_app.command("create")
def create(
    goal: str = typer.Argument(..., help="Goal description."),
    model: str = typer.Option("ollama/qwen3:8b", "--model", "-m", help="Model for estimation."),
    auto_approve: bool = typer.Option(False, "--yes", "-y", help="Auto-approve the plan."),
) -> None:
    """Create an execution plan with cost estimation."""
    c = _get_container()
    with console.status("[blue]Planning...[/]"):
        try:
            plan = _run(c.interactive_plan.create_plan(goal, model=model))
        except Exception as exc:
            print_error(str(exc))
            raise typer.Exit(code=1) from exc

    _print_plan(plan)

    if auto_approve:
        _do_approve(c, plan.id)
        return

    if typer.confirm("\nApprove this plan?"):
        _do_approve(c, plan.id)
    else:
        _run(c.interactive_plan.reject_plan(plan.id))
        console.print("[yellow]Plan rejected.[/]")


@plan_app.command("list")
def list_plans() -> None:
    """List all plans."""
    c = _get_container()
    plans = _run(c.plan_repo.list_all())
    if not plans:
        console.print("[dim]No plans found.[/]")
        return

    from rich.table import Table

    table = Table(title="Plans")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Goal", min_width=20)
    table.add_column("Status")
    table.add_column("Steps", justify="right")
    table.add_column("Est. Cost", justify="right")

    for p in plans:
        table.add_row(
            p.id[:8],
            p.goal[:60],
            p.status.value,
            str(len(p.steps)),
            f"${p.total_estimated_cost_usd:.4f}",
        )
    console.print(table)


@plan_app.command("show")
def show(
    plan_id: str = typer.Argument(..., help="Plan ID to show."),
) -> None:
    """Show details of a specific plan."""
    c = _get_container()
    plan = _run(c.plan_repo.get_by_id(plan_id))
    if plan is None:
        print_error(f"Plan {plan_id} not found")
        raise typer.Exit(code=1)
    _print_plan(plan)


@plan_app.command("approve")
def approve(
    plan_id: str = typer.Argument(..., help="Plan ID to approve."),
) -> None:
    """Approve a plan and create the task."""
    c = _get_container()
    _do_approve(c, plan_id)


@plan_app.command("reject")
def reject(
    plan_id: str = typer.Argument(..., help="Plan ID to reject."),
) -> None:
    """Reject a plan."""
    from application.use_cases.interactive_plan import PlanAlreadyDecidedError, PlanNotFoundError

    c = _get_container()
    try:
        _run(c.interactive_plan.reject_plan(plan_id))
    except PlanNotFoundError as e:
        print_error(f"Plan {plan_id} not found")
        raise typer.Exit(code=1) from e
    except PlanAlreadyDecidedError as e:
        print_error(str(e))
        raise typer.Exit(code=1) from e
    console.print("[yellow]Plan rejected.[/]")


def _do_approve(c, plan_id: str) -> None:  # noqa: ANN001
    """Approve a plan and display the resulting task."""
    from application.use_cases.interactive_plan import PlanAlreadyDecidedError, PlanNotFoundError

    try:
        task = _run(c.interactive_plan.approve_plan(plan_id))
    except PlanNotFoundError as e:
        print_error(f"Plan {plan_id} not found")
        raise typer.Exit(code=1) from e
    except PlanAlreadyDecidedError as e:
        print_error(str(e))
        raise typer.Exit(code=1) from e

    console.print(f"[green]Plan approved![/] Task created: {task.id[:8]}")

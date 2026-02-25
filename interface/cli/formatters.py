"""Rich formatting utilities for CLI output.

All rich console output is isolated here — keeps commands thin and testable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table
from rich.tree import Tree

if TYPE_CHECKING:
    from domain.entities.task import TaskEntity

console = Console()

# Status → (style, symbol) mapping
STATUS_STYLES: dict[str, tuple[str, str]] = {
    "pending": ("yellow", "..."),
    "running": ("blue bold", ">>>"),
    "success": ("green", "OK"),
    "failed": ("red", "ERR"),
    "fallback": ("yellow", "FBK"),
}


def print_error(message: str) -> None:
    """Print a styled error message to stderr."""
    console.print(f"[red bold]Error:[/] {message}", style="red")


# ── Task formatters ──


def _status_text(status: str) -> str:
    style, symbol = STATUS_STYLES.get(status, ("white", "?"))
    return f"[{style}]{symbol} {status}[/]"


def print_task_table(tasks: list[TaskEntity]) -> None:
    """Print a table of tasks."""
    if not tasks:
        console.print("[dim]No tasks found.[/]")
        return

    table = Table(title="Tasks")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Goal", min_width=20)
    table.add_column("Status")
    table.add_column("Subtasks", justify="right")
    table.add_column("Cost", justify="right")

    for t in tasks:
        table.add_row(
            t.id[:8],
            t.goal[:60],
            _status_text(t.status.value),
            str(len(t.subtasks)),
            f"${t.total_cost_usd:.4f}",
        )
    console.print(table)


def print_task_detail(task: TaskEntity) -> None:
    """Print a tree view of a single task with its subtasks."""
    tree = Tree(f"[bold]{task.goal}[/] ({_status_text(task.status.value)})")
    tree.add(f"ID: [dim]{task.id}[/]")
    tree.add(f"Cost: ${task.total_cost_usd:.4f}")
    tree.add(f"Success rate: {task.success_rate:.0%}")

    if task.subtasks:
        st_branch = tree.add("[bold]Subtasks[/]")
        for st in task.subtasks:
            label = f"{_status_text(st.status.value)} {st.description}"
            if st.result:
                label += f" → {st.result[:80]}"
            st_branch.add(label)

    console.print(tree)


# ── Model formatters ──


def print_model_table(models: list[str]) -> None:
    """Print a table of available models."""
    if not models:
        console.print("[dim]No models found.[/]")
        return

    table = Table(title="Models")
    table.add_column("Name")
    table.add_column("Type", justify="center")

    for name in models:
        tag = "[green]LOCAL[/]"
        table.add_row(name, tag)
    console.print(table)


def print_model_status(running: bool, models: list[str], default_model: str) -> None:
    """Print Ollama status overview."""
    status = "[green]Running[/]" if running else "[red]Stopped[/]"
    console.print(f"Ollama: {status}")
    console.print(f"Default model: [bold]{default_model}[/]")
    if models:
        console.print(f"Installed: {', '.join(models)}")
    else:
        console.print("[dim]No models installed.[/]")


# ── Cost formatters ──


def print_cost_summary(
    daily_usd: float,
    monthly_usd: float,
    local_rate: float,
    budget_usd: float,
    remaining_usd: float,
) -> None:
    """Print cost summary table."""
    table = Table(title="Cost Summary")
    table.add_column("Metric")
    table.add_column("Value", justify="right")

    table.add_row("Daily total", f"${daily_usd:.4f}")
    table.add_row("Monthly total", f"${monthly_usd:.4f}")

    rate_style = "green" if local_rate >= 0.8 else "yellow" if local_rate >= 0.5 else "red"
    table.add_row("Local usage rate", f"[{rate_style}]{local_rate:.0%}[/]")

    table.add_row("Monthly budget", f"${budget_usd:.2f}")

    remaining_style = "green" if remaining_usd > budget_usd * 0.5 else "yellow"
    table.add_row("Budget remaining", f"[{remaining_style}]${remaining_usd:.2f}[/]")

    console.print(table)

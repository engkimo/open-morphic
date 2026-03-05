"""Rich formatting utilities for CLI output.

All rich console output is isolated here — keeps commands thin and testable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table
from rich.tree import Tree

if TYPE_CHECKING:
    from application.use_cases.route_to_engine import EngineStatus
    from domain.entities.task import TaskEntity
    from domain.entities.tool_candidate import ToolCandidate
    from domain.ports.agent_engine import AgentEngineResult

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


def print_model_detail(name: str, details: dict) -> None:
    """Print detailed model info."""
    if not details:
        console.print(f"[dim]No details available for {name}.[/]")
        return

    tree = Tree(f"[bold]{name}[/]")
    for key, value in details.items():
        if isinstance(value, dict):
            branch = tree.add(f"[bold]{key}[/]")
            for k, v in value.items():
                branch.add(f"{k}: {v}")
        elif isinstance(value, str) and len(value) > 200:
            tree.add(f"{key}: [dim]{value[:200]}...[/]")
        else:
            tree.add(f"{key}: {value}")
    console.print(tree)


def print_model_status(running: bool, models: list[str], default_model: str) -> None:
    """Print Ollama status overview."""
    status = "[green]Running[/]" if running else "[red]Stopped[/]"
    console.print(f"Ollama: {status}")
    console.print(f"Default model: [bold]{default_model}[/]")
    if models:
        console.print(f"Installed: {', '.join(models)}")
    else:
        console.print("[dim]No models installed.[/]")


# ── Engine formatters ──


def print_engine_table(engines: list[EngineStatus]) -> None:
    """Print a table of agent execution engines."""
    if not engines:
        console.print("[dim]No engines registered.[/]")
        return

    table = Table(title="Agent Engines")
    table.add_column("Engine", min_width=12)
    table.add_column("Available", justify="center")
    table.add_column("Context", justify="right")
    table.add_column("Sandbox", justify="center")
    table.add_column("Parallel", justify="center")
    table.add_column("MCP", justify="center")
    table.add_column("$/hr", justify="right")

    for e in engines:
        caps = e.capabilities
        avail = "[green]Yes[/]" if e.available else "[red]No[/]"
        ctx = f"{caps.max_context_tokens:,}"
        sandbox = "[green]Yes[/]" if caps.supports_sandbox else "[dim]-[/]"
        parallel = "[green]Yes[/]" if caps.supports_parallel else "[dim]-[/]"
        mcp = "[green]Yes[/]" if caps.supports_mcp else "[dim]-[/]"
        cost = "[green]FREE[/]" if caps.cost_per_hour_usd == 0 else f"${caps.cost_per_hour_usd:.2f}"

        table.add_row(e.engine_type.value, avail, ctx, sandbox, parallel, mcp, cost)

    console.print(table)


def print_engine_result(result: AgentEngineResult) -> None:
    """Print the result of an engine execution."""
    status = "[green]Success[/]" if result.success else "[red]Failed[/]"
    console.print(f"Engine: [bold]{result.engine.value}[/]  Status: {status}")
    if result.model_used:
        console.print(f"Model: {result.model_used}")
    console.print(f"Cost: ${result.cost_usd:.4f}  Duration: {result.duration_seconds:.1f}s")
    if result.error:
        console.print(f"[red]Error: {result.error}[/]")
    if result.output:
        console.print(f"\n{result.output}")


# ── Tool / Marketplace formatters ──

# Safety tier → (style, label) mapping
SAFETY_STYLES: dict[str, tuple[str, str]] = {
    "verified": ("green bold", "VERIFIED"),
    "community": ("cyan", "COMMUNITY"),
    "experimental": ("yellow", "EXPERIMENTAL"),
    "unsafe": ("red bold", "UNSAFE"),
}


def print_safety_badge(tier_name: str) -> str:
    """Return a rich-styled safety badge string."""
    style, label = SAFETY_STYLES.get(tier_name.lower(), ("dim", tier_name.upper()))
    return f"[{style}]{label}[/]"


def print_tool_table(tools: list[ToolCandidate]) -> None:
    """Print a table of tool candidates or installed tools."""
    if not tools:
        console.print("[dim]No tools found.[/]")
        return

    table = Table(title="Tools")
    table.add_column("Name", min_width=15)
    table.add_column("Publisher")
    table.add_column("Safety", justify="center")
    table.add_column("Score", justify="right")
    table.add_column("Transport")
    table.add_column("Downloads", justify="right")

    for t in tools:
        badge = print_safety_badge(t.safety_tier.name)
        table.add_row(
            t.name,
            t.publisher or "[dim]-[/]",
            badge,
            f"{t.safety_score:.2f}",
            t.transport,
            f"{t.download_count:,}" if t.download_count else "[dim]-[/]",
        )
    console.print(table)


def print_tool_detail(tool: ToolCandidate) -> None:
    """Print detailed info for a single tool."""
    badge = print_safety_badge(tool.safety_tier.name)
    tree = Tree(f"[bold]{tool.name}[/] {badge}")
    tree.add(f"Publisher: {tool.publisher or '[dim]unknown[/]'}")
    tree.add(f"Package: {tool.package_name or '[dim]unknown[/]'}")
    tree.add(f"Transport: {tool.transport}")
    tree.add(f"Score: {tool.safety_score:.2f}")
    if tool.description:
        tree.add(f"Description: {tool.description}")
    if tool.install_command:
        tree.add(f"Install: [dim]{tool.install_command}[/]")
    if tool.source_url:
        tree.add(f"Source: [dim]{tool.source_url}[/]")
    console.print(tree)


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

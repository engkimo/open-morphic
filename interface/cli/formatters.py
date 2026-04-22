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
    from domain.entities.execution_record import ExecutionRecord
    from domain.entities.fractal_learning import ErrorPattern, SuccessfulPath
    from domain.entities.memory import MemoryEntry
    from domain.entities.task import TaskEntity
    from domain.entities.tool_candidate import ToolCandidate
    from domain.ports.agent_engine import AgentEngineResult
    from domain.ports.execution_record_repository import ExecutionStats

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


# ---------- Cognitive / UCL ----------


def print_shared_state(state: dict) -> None:  # type: ignore[type-arg]
    """Print a single shared task state."""
    from rich.tree import Tree

    tree = Tree(f"[bold]Task: {state['task_id']}[/bold]")

    last = state.get("last_agent") or "none"
    tree.add(f"Last agent: [cyan]{last}[/cyan]")
    tree.add(f"Total cost: [yellow]${state.get('total_cost_usd', 0):.4f}[/yellow]")

    if state.get("decisions"):
        dec_branch = tree.add(f"Decisions ({len(state['decisions'])})")
        for d in state["decisions"][-5:]:
            dec_branch.add(
                f"[{d.get('agent_engine', '?')}] {d['description']}"
                f" (conf={d.get('confidence', 0):.0%})"
            )

    if state.get("artifacts"):
        art_branch = tree.add(f"Artifacts ({len(state['artifacts'])})")
        for k, v in list(state["artifacts"].items())[:10]:
            art_branch.add(f"{k}: {v[:80]}")

    if state.get("blockers"):
        blk_branch = tree.add(f"[red]Blockers ({len(state['blockers'])})[/red]")
        for b in state["blockers"]:
            blk_branch.add(f"[red]{b}[/red]")

    if state.get("agent_history"):
        hist_branch = tree.add(f"Agent history ({len(state['agent_history'])})")
        for a in state["agent_history"][-5:]:
            hist_branch.add(
                f"[{a.get('agent_engine', '?')}] {a.get('action_type', '?')}"
                f": {a.get('summary', '')[:60]}"
            )

    console.print(tree)


def print_state_list_table(states: list) -> None:  # type: ignore[type-arg]
    """Print a table of shared task states."""
    table = Table(title="Shared Task States")
    table.add_column("Task ID", max_width=36)
    table.add_column("Last Agent")
    table.add_column("Decisions", justify="right")
    table.add_column("Blockers", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Updated")

    for s in states:
        blocker_count = len(s.get("blockers", []))
        blocker_style = "red" if blocker_count > 0 else ""
        table.add_row(
            s["task_id"][:36],
            s.get("last_agent") or "-",
            str(len(s.get("decisions", []))),
            f"[{blocker_style}]{blocker_count}[/]" if blocker_style else str(blocker_count),
            f"${s.get('total_cost_usd', 0):.4f}",
            str(s.get("updated_at", ""))[:19],
        )

    console.print(table)


def print_affinity_table(scores: list) -> None:  # type: ignore[type-arg]
    """Print affinity scores table."""
    table = Table(title="Agent Affinity Scores")
    table.add_column("Engine")
    table.add_column("Topic")
    table.add_column("Score", justify="right")
    table.add_column("Familiarity", justify="right")
    table.add_column("Success", justify="right")
    table.add_column("Samples", justify="right")

    for s in scores:
        score_val = s.get("score", 0)
        score_style = "green" if score_val >= 0.7 else "yellow" if score_val >= 0.4 else "red"
        table.add_row(
            s["engine"],
            s["topic"],
            f"[{score_style}]{score_val:.2f}[/]",
            f"{s.get('familiarity', 0):.2f}",
            f"{s.get('success_rate', 0):.0%}",
            str(s.get("sample_count", 0)),
        )

    console.print(table)


# ── A2A formatters ──


def print_a2a_conversation_table(conversations: list) -> None:  # type: ignore[type-arg]
    """Print an overview table of A2A conversations."""
    table = Table(title="A2A Conversations")
    table.add_column("ID", max_width=12)
    table.add_column("Task ID")
    table.add_column("Participants")
    table.add_column("Status")
    table.add_column("Messages", justify="right")

    for conv in conversations:
        status = conv.status.value
        style = {"open": "blue", "resolved": "green", "timeout": "yellow", "error": "red"}.get(
            status, ""
        )
        table.add_row(
            conv.id[:12],
            conv.task_id,
            ", ".join(p.value for p in conv.participants),
            f"[{style}]{status}[/]",
            str(conv.message_count),
        )

    console.print(table)


def print_a2a_conversation_detail(conv, summary) -> None:  # type: ignore[type-arg]
    """Print detailed view of a single A2A conversation."""
    console.print(f"[bold]Conversation:[/] {conv.id}")
    console.print(f"Task: {conv.task_id}")
    console.print(f"Status: [bold]{conv.status.value}[/]")
    console.print(f"Participants: {', '.join(p.value for p in conv.participants)}")
    console.print(
        f"Messages: {summary.message_count} total, "
        f"{summary.response_count} responses, "
        f"{summary.pending_count} pending"
    )

    if conv.messages:
        console.print()
        print_a2a_message_table(conv.messages)


def print_a2a_message_table(messages: list) -> None:  # type: ignore[type-arg]
    """Print a table of A2A messages."""
    table = Table(title="Messages")
    table.add_column("ID", max_width=12)
    table.add_column("Type")
    table.add_column("Sender")
    table.add_column("Receiver")
    table.add_column("Action")
    table.add_column("Payload", max_width=40)

    for msg in messages:
        table.add_row(
            msg.id[:12],
            msg.message_type.value,
            msg.sender.value,
            msg.receiver.value if msg.receiver else "(broadcast)",
            msg.action.value,
            msg.payload[:40] if msg.payload else "",
        )

    console.print(table)


def print_conflict_table(conflicts: list) -> None:  # type: ignore[type-arg]
    """Print a table of detected conflict pairs."""
    table = Table(title=f"Conflicts Detected ({len(conflicts)})")
    table.add_column("Insight A", max_width=35)
    table.add_column("Engine A")
    table.add_column("Insight B", max_width=35)
    table.add_column("Engine B")
    table.add_column("Overlap", justify="right")
    table.add_column("Winner")

    for cp in conflicts:
        winner_label = "A" if cp.resolved_winner is cp.insight_a else "B"
        table.add_row(
            cp.insight_a.content[:35],
            cp.insight_a.source_engine.value,
            cp.insight_b.content[:35],
            cp.insight_b.source_engine.value,
            f"{cp.overlap_score:.0%}",
            f"[green]{winner_label}[/]",
        )

    console.print(table)


def print_model_preference_table(prefs: list) -> None:  # type: ignore[type-arg]
    """Print a table of learned model preferences."""
    table = Table(title="Model Preferences")
    table.add_column("Task Type")
    table.add_column("Model")
    table.add_column("Success", justify="right")
    table.add_column("Avg Cost", justify="right")
    table.add_column("Avg Time", justify="right")
    table.add_column("Samples", justify="right")

    for p in prefs:
        rate_style = (
            "green" if p.success_rate >= 0.8 else "yellow" if p.success_rate >= 0.5 else "red"
        )
        table.add_row(
            p.task_type.value,
            p.model,
            f"[{rate_style}]{p.success_rate:.0%}[/]",
            f"${p.avg_cost_usd:.4f}",
            f"{p.avg_duration_seconds:.1f}s",
            str(p.sample_count),
        )

    console.print(table)


def print_engine_preference_table(prefs: list) -> None:  # type: ignore[type-arg]
    """Print a table of learned engine preferences."""
    table = Table(title="Engine Preferences")
    table.add_column("Task Type")
    table.add_column("Engine")
    table.add_column("Success", justify="right")
    table.add_column("Avg Cost", justify="right")
    table.add_column("Avg Time", justify="right")
    table.add_column("Samples", justify="right")

    for p in prefs:
        rate_style = (
            "green" if p.success_rate >= 0.8 else "yellow" if p.success_rate >= 0.5 else "red"
        )
        table.add_row(
            p.task_type.value,
            p.engine.value,
            f"[{rate_style}]{p.success_rate:.0%}[/]",
            f"${p.avg_cost_usd:.4f}",
            f"{p.avg_duration_seconds:.1f}s",
            str(p.sample_count),
        )

    console.print(table)


def print_recovery_rule_table(rules: list) -> None:  # type: ignore[type-arg]
    """Print a table of learned recovery rules."""
    table = Table(title="Recovery Rules")
    table.add_column("Error Pattern", max_width=40)
    table.add_column("Failed Tool")
    table.add_column("Alternative")
    table.add_column("Success", justify="right")
    table.add_column("Attempts", justify="right")

    for r in rules:
        rate_style = (
            "green" if r.success_rate >= 0.8 else "yellow" if r.success_rate >= 0.5 else "red"
        )
        table.add_row(
            r.error_pattern[:40],
            r.failed_tool or "-",
            r.alternative_tool,
            f"[{rate_style}]{r.success_rate:.0%}[/]",
            str(r.total_attempts),
        )

    console.print(table)


# ── Memory formatters ──

# Memory type → (style, label)
MEMORY_TYPE_STYLES: dict[str, tuple[str, str]] = {
    "l1_active": ("blue bold", "L1 Active"),
    "l2_semantic": ("cyan", "L2 Semantic"),
    "l3_facts": ("magenta", "L3 Facts"),
    "l4_cold": ("dim", "L4 Cold"),
}


def print_memory_table(entries: list[MemoryEntry]) -> None:
    """Print a table of memory entries."""
    if not entries:
        console.print("[dim]No memory entries found.[/]")
        return

    table = Table(title=f"Memory Entries ({len(entries)})")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Type", justify="center")
    table.add_column("Content", min_width=30, max_width=50)
    table.add_column("Importance", justify="right")
    table.add_column("Access", justify="right")
    table.add_column("Last Accessed")

    for e in entries:
        style, label = MEMORY_TYPE_STYLES.get(
            e.memory_type.value, ("white", e.memory_type.value)
        )
        imp_style = (
            "green" if e.importance_score >= 0.7
            else "yellow" if e.importance_score >= 0.4
            else "dim"
        )
        table.add_row(
            e.id[:12],
            f"[{style}]{label}[/]",
            e.content[:50],
            f"[{imp_style}]{e.importance_score:.2f}[/]",
            str(e.access_count),
            str(e.last_accessed)[:19],
        )

    console.print(table)


def print_memory_detail(entry: MemoryEntry) -> None:
    """Print detailed view of a single memory entry."""
    style, label = MEMORY_TYPE_STYLES.get(
        entry.memory_type.value, ("white", entry.memory_type.value)
    )
    tree = Tree(f"[bold]Memory:[/] {entry.id}")
    tree.add(f"Type: [{style}]{label}[/]")
    tree.add(f"Importance: {entry.importance_score:.2f}")
    tree.add(f"Access count: {entry.access_count}")
    tree.add(f"Created: {entry.created_at}")
    tree.add(f"Last accessed: {entry.last_accessed}")

    content_branch = tree.add("[bold]Content[/]")
    content_branch.add(entry.content)

    if entry.metadata:
        meta_branch = tree.add("[bold]Metadata[/]")
        for k, v in entry.metadata.items():
            meta_branch.add(f"{k}: {v}")

    console.print(tree)


def print_memory_stats(
    type_counts: dict[str, int],
    total_entries: int,
    total_access: int,
    max_importance: float,
) -> None:
    """Print memory statistics table."""
    table = Table(title="Memory Statistics")
    table.add_column("Metric")
    table.add_column("Value", justify="right")

    table.add_row("Total entries", str(total_entries))
    table.add_row("Total access count", str(total_access))
    table.add_row("Max importance", f"{max_importance:.2f}")

    table.add_section()
    for type_name, count in type_counts.items():
        style, label = MEMORY_TYPE_STYLES.get(type_name, ("white", type_name))
        table.add_row(f"[{style}]{label}[/]", str(count))

    console.print(table)


# ── Execution / Fallback formatters ──


def print_execution_history_table(records: list[ExecutionRecord]) -> None:
    """Print a table of execution records with engine routing info."""
    if not records:
        console.print("[dim]No execution records found.[/]")
        return

    table = Table(title=f"Execution History ({len(records)})")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Goal", max_width=35)
    table.add_column("Engine")
    table.add_column("Model")
    table.add_column("Status", justify="center")
    table.add_column("Cost", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Time")

    for r in records:
        status = "[green]OK[/]" if r.success else "[red]FAIL[/]"
        error_hint = ""
        if r.error_message:
            error_hint = f" [dim]({r.error_message[:30]})[/]"
        table.add_row(
            r.id[:8],
            r.goal[:35] if r.goal else r.task_id[:35],
            r.engine_used.value,
            r.model_used or "-",
            f"{status}{error_hint}",
            f"${r.cost_usd:.4f}",
            f"{r.duration_seconds:.1f}s",
            str(r.created_at)[:19],
        )

    console.print(table)


def print_execution_stats(stats: ExecutionStats) -> None:
    """Print aggregated execution statistics."""
    table = Table(title="Execution Statistics")
    table.add_column("Metric")
    table.add_column("Value", justify="right")

    rate_style = (
        "green" if stats.success_rate >= 0.8
        else "yellow" if stats.success_rate >= 0.5
        else "red"
    )
    table.add_row("Total executions", str(stats.total_count))
    table.add_row("Successes", f"[green]{stats.success_count}[/]")
    table.add_row("Failures", f"[red]{stats.failure_count}[/]")
    table.add_row(
        "Success rate", f"[{rate_style}]{stats.success_rate:.0%}[/]"
    )
    table.add_row("Avg cost", f"${stats.avg_cost_usd:.4f}")
    table.add_row("Avg duration", f"{stats.avg_duration_seconds:.1f}s")

    if stats.engine_distribution:
        table.add_section()
        for engine, count in sorted(
            stats.engine_distribution.items(),
            key=lambda x: x[1],
            reverse=True,
        ):
            table.add_row(f"Engine: {engine}", str(count))

    if stats.model_distribution:
        table.add_section()
        for model, count in sorted(
            stats.model_distribution.items(),
            key=lambda x: x[1],
            reverse=True,
        ):
            table.add_row(f"Model: {model}", str(count))

    console.print(table)


def print_agent_table(agents: list) -> None:  # type: ignore[type-arg]
    """Print a table of registered agents."""
    table = Table(title="Registered Agents")
    table.add_column("Agent ID", max_width=12)
    table.add_column("Engine")
    table.add_column("Capabilities")
    table.add_column("Status")

    for agent in agents:
        status = agent.status
        style = "green" if status == "available" else "dim"
        table.add_row(
            agent.agent_id[:12],
            agent.engine_type.value,
            ", ".join(agent.capabilities) if agent.capabilities else "(none)",
            f"[{style}]{status}[/]",
        )

    console.print(table)


# ── Learning / Fractal formatters ──


def print_error_pattern_table(patterns: list[ErrorPattern]) -> None:
    """Print a table of fractal learning error patterns."""
    if not patterns:
        console.print("[dim]No error patterns found.[/]")
        return

    table = Table(title=f"Error Patterns ({len(patterns)})")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Goal Fragment", max_width=30)
    table.add_column("Node", max_width=25)
    table.add_column("Error", max_width=35)
    table.add_column("Count", justify="right")
    table.add_column("Last Seen")

    for p in patterns:
        count_style = "red" if p.occurrence_count >= 5 else "yellow"
        table.add_row(
            p.id[:8],
            p.goal_fragment[:30],
            p.node_description[:25],
            p.error_message[:35],
            f"[{count_style}]{p.occurrence_count}[/]",
            str(p.last_seen)[:19],
        )

    console.print(table)


def print_successful_path_table(paths: list[SuccessfulPath]) -> None:
    """Print a table of fractal learning successful paths."""
    if not paths:
        console.print("[dim]No successful paths found.[/]")
        return

    table = Table(title=f"Successful Paths ({len(paths)})")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Goal Fragment", max_width=30)
    table.add_column("Nodes", max_width=40)
    table.add_column("Cost", justify="right")
    table.add_column("Usage", justify="right")
    table.add_column("Last Used")

    for p in paths:
        nodes_str = " → ".join(
            n[:15] for n in p.node_descriptions[:3]
        )
        if len(p.node_descriptions) > 3:
            nodes_str += f" (+{len(p.node_descriptions) - 3})"
        table.add_row(
            p.id[:8],
            p.goal_fragment[:30],
            nodes_str,
            f"${p.total_cost_usd:.4f}",
            f"[green]{p.usage_count}[/]",
            str(p.last_used)[:19],
        )

    console.print(table)


def print_export_result(result) -> None:  # type: ignore[type-arg]
    """Print a single context export result."""
    console.print(
        f"[bold]Platform:[/] [cyan]{result.platform}[/]  "
        f"(~{result.token_estimate} tokens)\n"
    )
    console.print(result.content)


def print_export_results_table(results: list) -> None:  # type: ignore[type-arg]
    """Print a summary table of all platform exports."""
    if not results:
        console.print("[dim]No export results.[/]")
        return

    table = Table(title="Context Exports")
    table.add_column("Platform")
    table.add_column("Tokens", justify="right")
    table.add_column("Preview", max_width=50)

    for r in results:
        preview = r.content.replace("\n", " ")[:50]
        table.add_row(
            f"[cyan]{r.platform}[/]",
            str(r.token_estimate),
            preview,
        )

    console.print(table)
    console.print(
        f"\n[dim]Total: {sum(r.token_estimate for r in results)} tokens "
        f"across {len(results)} platforms[/]"
    )


def print_learning_stats(
    patterns: list[ErrorPattern],
    paths: list[SuccessfulPath],
) -> None:
    """Print learning data statistics."""
    table = Table(title="Learning Statistics")
    table.add_column("Metric")
    table.add_column("Value", justify="right")

    table.add_row("Error patterns", str(len(patterns)))
    table.add_row("Successful paths", str(len(paths)))

    if patterns:
        total_occ = sum(p.occurrence_count for p in patterns)
        table.add_row("Total error occurrences", str(total_occ))
        top = max(patterns, key=lambda p: p.occurrence_count)
        table.add_row(
            "Most frequent error",
            f"{top.goal_fragment[:25]} ({top.occurrence_count}x)",
        )

    if paths:
        total_usage = sum(p.usage_count for p in paths)
        avg_cost = sum(p.total_cost_usd for p in paths) / len(paths)
        table.add_row("Total path usages", str(total_usage))
        table.add_row("Avg path cost", f"${avg_cost:.4f}")

    console.print(table)

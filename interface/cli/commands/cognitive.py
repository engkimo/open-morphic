"""UCL / Cognitive CLI commands — shared task state, affinity, handoff, insights."""

from __future__ import annotations

import typer

from interface.cli._utils import _get_container, _run
from interface.cli.formatters import (
    console,
    print_affinity_table,
    print_conflict_table,
    print_error,
    print_shared_state,
    print_state_list_table,
)

cognitive_app = typer.Typer()


@cognitive_app.command("state")
def state_cmd(
    task_id: str | None = typer.Argument(None, help="Task ID (omit to list all)"),
) -> None:
    """Show shared task state (or list all active states)."""
    c = _get_container()

    if task_id:
        result = _run(c.shared_task_state_repo.get(task_id))
        if result is None:
            print_error(f"No shared state for task {task_id}")
            raise typer.Exit(code=1)
        from interface.api.schemas import SharedTaskStateResponse

        data = SharedTaskStateResponse.from_state(result).model_dump()
        print_shared_state(data)
    else:
        states = _run(c.shared_task_state_repo.list_active())
        if not states:
            console.print("[dim]No active shared states.[/dim]")
            return
        from interface.api.schemas import SharedTaskStateResponse

        data = [SharedTaskStateResponse.from_state(s).model_dump() for s in states]
        print_state_list_table(data)


@cognitive_app.command("delete")
def delete_cmd(task_id: str = typer.Argument(..., help="Task ID to delete")) -> None:
    """Delete a shared task state."""
    c = _get_container()
    result = _run(c.shared_task_state_repo.get(task_id))
    if result is None:
        print_error(f"No shared state for task {task_id}")
        raise typer.Exit(code=1)
    _run(c.shared_task_state_repo.delete(task_id))
    console.print(f"[green]Deleted shared state for {task_id}[/green]")


@cognitive_app.command("affinity")
def affinity_cmd(
    topic: str | None = typer.Option(None, "--topic", "-t", help="Filter by topic"),
    engine: str | None = typer.Option(None, "--engine", "-e", help="Filter by engine"),
) -> None:
    """List agent affinity scores."""
    from domain.services.agent_affinity import AgentAffinityScorer
    from domain.value_objects.agent_engine import AgentEngineType

    c = _get_container()

    if topic:
        scores = _run(c.affinity_repo.get_by_topic(topic))
    elif engine:
        try:
            engine_type = AgentEngineType(engine)
        except ValueError:
            print_error(f"Unknown engine: {engine}")
            raise typer.Exit(code=1) from None
        scores = _run(c.affinity_repo.get_by_engine(engine_type))
    else:
        scores = _run(c.affinity_repo.list_all())

    if not scores:
        console.print("[dim]No affinity scores recorded.[/dim]")
        return

    data = [
        {
            "engine": s.engine.value,
            "topic": s.topic,
            "score": AgentAffinityScorer.score(s),
            "familiarity": s.familiarity,
            "success_rate": s.success_rate,
            "sample_count": s.sample_count,
        }
        for s in scores
    ]
    print_affinity_table(data)


@cognitive_app.command("handoff")
def handoff_cmd(
    task: str = typer.Argument(..., help="Task description"),
    task_id: str = typer.Option(..., "--task-id", "-i", help="Task ID"),
    source: str = typer.Option(..., "--source", "-s", help="Source engine"),
    reason: str = typer.Option(..., "--reason", "-r", help="Reason for handoff"),
    target: str | None = typer.Option(None, "--target", "-t", help="Target engine"),
    budget: float = typer.Option(1.0, "--budget", "-b", help="Budget USD"),
) -> None:
    """Hand off a task from one engine to another."""
    from application.use_cases.handoff_task import HandoffRequest
    from domain.value_objects.agent_engine import AgentEngineType

    c = _get_container()

    try:
        source_engine = AgentEngineType(source)
    except ValueError:
        print_error(f"Unknown source engine: {source}")
        raise typer.Exit(code=1) from None

    target_engine = None
    if target:
        try:
            target_engine = AgentEngineType(target)
        except ValueError:
            print_error(f"Unknown target engine: {target}")
            raise typer.Exit(code=1) from None

    with console.status("[blue]Executing handoff...[/]"):
        req = HandoffRequest(
            task=task,
            task_id=task_id,
            source_engine=source_engine,
            reason=reason,
            target_engine=target_engine,
            budget=budget,
        )
        result = _run(c.handoff_task.handoff(req))

    if result.success:
        console.print(
            f"[green]Handoff successful:[/green] "
            f"{result.source_engine.value} -> {result.target_engine.value}"
        )
        if result.engine_result:
            console.print(f"Output: {result.engine_result.output[:200]}")
    else:
        print_error(f"Handoff failed: {result.error}")
        raise typer.Exit(code=1)


@cognitive_app.command("insights")
def insights_cmd(
    task_id: str = typer.Option(..., "--task-id", "-i", help="Task ID"),
    engine: str = typer.Option(..., "--engine", "-e", help="Engine type"),
    output: str = typer.Option(..., "--output", "-o", help="Agent output text"),
) -> None:
    """Extract insights from agent output."""
    from domain.value_objects.agent_engine import AgentEngineType

    c = _get_container()

    try:
        engine_type = AgentEngineType(engine)
    except ValueError:
        print_error(f"Unknown engine: {engine}")
        raise typer.Exit(code=1) from None

    with console.status("[blue]Extracting insights...[/]"):
        insights = _run(
            c.extract_insights.extract_and_store(
                task_id=task_id,
                engine=engine_type,
                output=output,
            )
        )

    if not insights:
        console.print("[dim]No insights extracted.[/dim]")
        return

    from rich.table import Table

    table = Table(title=f"Extracted Insights ({len(insights)})")
    table.add_column("Type")
    table.add_column("Content", max_width=60)
    table.add_column("Confidence", justify="right")
    table.add_column("Engine")

    for i in insights:
        table.add_row(
            i.memory_type.value,
            i.content[:60],
            f"{i.confidence:.0%}",
            i.source_engine.value,
        )

    console.print(table)


@cognitive_app.command("conflicts")
def conflicts_cmd(
    resolve: bool = typer.Option(
        False, "--resolve", "-r", help="Apply resolution and show survivors"
    ),
    limit: int = typer.Option(100, "--limit", "-n", help="Max memories to analyze"),
) -> None:
    """Detect conflicts between stored insights from different engines."""
    from domain.ports.insight_extractor import ExtractedInsight
    from domain.services.conflict_resolver import ConflictResolver
    from domain.value_objects.agent_engine import AgentEngineType
    from domain.value_objects.cognitive import CognitiveMemoryType
    from domain.value_objects.status import MemoryType

    c = _get_container()

    # Fetch memories from L1-L3 (most likely to have cross-engine insights)
    reverse_type_map = {
        MemoryType.L2_SEMANTIC: CognitiveMemoryType.EPISODIC,
        MemoryType.L3_FACTS: CognitiveMemoryType.SEMANTIC,
        MemoryType.L1_ACTIVE: CognitiveMemoryType.WORKING,
    }
    memories: list = []
    for mt in (MemoryType.L2_SEMANTIC, MemoryType.L3_FACTS, MemoryType.L1_ACTIVE):
        memories.extend(_run(c.memory_repo.list_by_type(mt, limit=limit)))

    if not memories:
        console.print("[dim]No memories found to analyze.[/dim]")
        return

    # Convert MemoryEntry → ExtractedInsight
    insights: list[ExtractedInsight] = []
    for m in memories:
        engine_str = m.metadata.get("source_engine", "ollama")
        try:
            engine = AgentEngineType(engine_str)
        except ValueError:
            engine = AgentEngineType.OLLAMA
        insights.append(
            ExtractedInsight(
                content=m.content,
                memory_type=reverse_type_map.get(
                    m.memory_type, CognitiveMemoryType.EPISODIC
                ),
                confidence=m.importance_score,
                source_engine=engine,
                tags=m.metadata.get("tags", []),
            )
        )

    if resolve:
        survivors, conflicts = ConflictResolver.resolve_all(insights)
        if not conflicts:
            console.print(
                f"[dim]No conflicts detected among {len(insights)} insights.[/dim]"
            )
            return
        print_conflict_table(conflicts)
        console.print(
            f"\n[green]Resolved: {len(survivors)} survivors, "
            f"{len(conflicts)} conflicts removed[/green]"
        )
    else:
        conflicts = ConflictResolver.detect_conflicts(insights)
        if not conflicts:
            console.print(
                f"[dim]No conflicts detected among {len(insights)} insights.[/dim]"
            )
            return
        print_conflict_table(conflicts)

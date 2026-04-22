"""A2A (Agent-to-Agent) CLI commands — conversations, messaging, and agent registry."""

from __future__ import annotations

import typer

from interface.cli._utils import _get_container, _run
from interface.cli.formatters import (
    console,
    print_a2a_conversation_detail,
    print_a2a_conversation_table,
    print_agent_table,
    print_error,
)

a2a_app = typer.Typer()


@a2a_app.command("create")
def create_cmd(
    task_id: str = typer.Argument(..., help="Task ID for this conversation"),
    participants: str = typer.Option(
        ...,
        "--participants",
        "-p",
        help="Comma-separated engine list (e.g. claude_code,gemini_cli)",
    ),
    ttl: int = typer.Option(300, "--ttl", help="Timeout in seconds"),
) -> None:
    """Create a new A2A conversation."""
    from domain.value_objects.agent_engine import AgentEngineType

    c = _get_container()

    try:
        participant_list = [AgentEngineType(p.strip()) for p in participants.split(",")]
    except ValueError as exc:
        print_error(f"Invalid engine type: {exc}")
        raise typer.Exit(code=1) from None

    conv = c.manage_a2a_conversation.create(
        task_id=task_id,
        participants=participant_list,
        ttl_seconds=ttl,
    )
    c.a2a_conversations[conv.id] = conv
    console.print(f"[green]Created conversation:[/] {conv.id}")
    console.print(f"Task: {conv.task_id}")
    console.print(f"Participants: {', '.join(p.value for p in conv.participants)}")
    console.print(f"TTL: {ttl}s")


@a2a_app.command("list")
def list_cmd() -> None:
    """List all A2A conversations."""
    c = _get_container()
    convs = list(c.a2a_conversations.values())
    if not convs:
        console.print("[dim]No conversations.[/dim]")
        return
    print_a2a_conversation_table(convs)


@a2a_app.command("show")
def show_cmd(
    conversation_id: str = typer.Argument(..., help="Conversation ID"),
) -> None:
    """Show conversation state and messages."""
    c = _get_container()
    conv = c.a2a_conversations.get(conversation_id)
    if conv is None:
        print_error(f"Conversation {conversation_id} not found")
        raise typer.Exit(code=1)
    summary = c.manage_a2a_conversation.summarize(conv)
    print_a2a_conversation_detail(conv, summary)


@a2a_app.command("send")
def send_cmd(
    conversation_id: str = typer.Argument(..., help="Conversation ID"),
    sender: str = typer.Option(..., "--sender", "-s", help="Sender engine type"),
    action: str = typer.Option(
        ..., "--action", "-a", help="A2A action (solve/review/synthesize/delegate/critique/inform)"
    ),
    payload: str = typer.Option(..., "--payload", "-m", help="Message content"),
    receiver: str | None = typer.Option(
        None, "--receiver", "-r", help="Target engine (auto-route if omitted)"
    ),
) -> None:
    """Send an A2A message in a conversation."""
    from domain.value_objects.a2a import A2AAction
    from domain.value_objects.agent_engine import AgentEngineType

    c = _get_container()
    conv = c.a2a_conversations.get(conversation_id)
    if conv is None:
        print_error(f"Conversation {conversation_id} not found")
        raise typer.Exit(code=1)

    try:
        sender_engine = AgentEngineType(sender)
    except ValueError:
        print_error(f"Unknown sender engine: {sender}")
        raise typer.Exit(code=1) from None

    try:
        a2a_action = A2AAction(action)
    except ValueError:
        print_error(f"Unknown action: {action}. Valid: {', '.join(a.value for a in A2AAction)}")
        raise typer.Exit(code=1) from None

    receiver_engine = None
    if receiver:
        try:
            receiver_engine = AgentEngineType(receiver)
        except ValueError:
            print_error(f"Unknown receiver engine: {receiver}")
            raise typer.Exit(code=1) from None

    with console.status("[blue]Sending message...[/]"):
        result = _run(
            c.send_a2a_message.execute(
                sender=sender_engine,
                action=a2a_action,
                conversation=conv,
                payload=payload,
                receiver=receiver_engine,
            )
        )

    console.print(f"[green]Sent:[/] {result.message_id}")
    if result.routed and result.receiver:
        console.print(f"[dim]Auto-routed to {result.receiver.value}[/]")
    elif result.receiver:
        console.print(f"[dim]Sent to {result.receiver.value}[/]")


@a2a_app.command("reply")
def reply_cmd(
    conversation_id: str = typer.Argument(..., help="Conversation ID"),
    message_id: str = typer.Argument(..., help="Message ID to reply to"),
    sender: str = typer.Option(..., "--sender", "-s", help="Sender engine type"),
    payload: str = typer.Option(..., "--payload", "-m", help="Reply content"),
) -> None:
    """Reply to a specific A2A message."""
    from domain.value_objects.agent_engine import AgentEngineType

    c = _get_container()
    conv = c.a2a_conversations.get(conversation_id)
    if conv is None:
        print_error(f"Conversation {conversation_id} not found")
        raise typer.Exit(code=1)

    request_msg = next((m for m in conv.messages if m.id == message_id), None)
    if request_msg is None:
        print_error(f"Message {message_id} not found in conversation")
        raise typer.Exit(code=1)

    try:
        sender_engine = AgentEngineType(sender)
    except ValueError:
        print_error(f"Unknown sender engine: {sender}")
        raise typer.Exit(code=1) from None

    with console.status("[blue]Sending reply...[/]"):
        result = _run(
            c.send_a2a_message.reply(
                sender=sender_engine,
                request=request_msg,
                conversation=conv,
                payload=payload,
            )
        )

    console.print(f"[green]Replied:[/] {result.message_id}")


@a2a_app.command("check")
def check_cmd(
    conversation_id: str = typer.Argument(..., help="Conversation ID"),
) -> None:
    """Check if a conversation is complete or expired."""
    c = _get_container()
    conv = c.a2a_conversations.get(conversation_id)
    if conv is None:
        print_error(f"Conversation {conversation_id} not found")
        raise typer.Exit(code=1)

    expired = c.manage_a2a_conversation.check_expired(conv)
    complete = c.manage_a2a_conversation.check_complete(conv)

    console.print(f"Status: [bold]{conv.status.value}[/]")
    if expired:
        console.print("[yellow]Conversation has expired.[/]")
    elif complete:
        console.print("[green]All participants have responded.[/]")
    else:
        console.print("[dim]Conversation is still open.[/]")


@a2a_app.command("collect")
def collect_cmd(
    conversation_id: str = typer.Argument(..., help="Conversation ID"),
    timeout: float = typer.Option(10.0, "--timeout", "-t", help="Poll timeout seconds"),
) -> None:
    """Poll for new replies in a conversation."""
    c = _get_container()
    conv = c.a2a_conversations.get(conversation_id)
    if conv is None:
        print_error(f"Conversation {conversation_id} not found")
        raise typer.Exit(code=1)

    with console.status("[blue]Collecting replies...[/]"):
        new_count = _run(c.manage_a2a_conversation.collect_replies(conv, timeout))

    console.print(f"[green]Collected {new_count} new replies[/]")
    console.print(f"Total messages: {conv.message_count}")


@a2a_app.command("agents")
def agents_cmd() -> None:
    """List registered agents."""
    c = _get_container()
    agents = _run(c.agent_registry.list_available())
    if not agents:
        console.print("[dim]No agents registered.[/dim]")
        return
    print_agent_table(agents)


@a2a_app.command("register")
def register_cmd(
    engine: str = typer.Option(..., "--engine", "-e", help="Engine type"),
    capabilities: str = typer.Option(
        "",
        "--capabilities",
        "-c",
        help="Comma-separated capabilities (e.g. code,review,test)",
    ),
) -> None:
    """Register an agent in the A2A registry."""
    from domain.entities.a2a import AgentDescriptor
    from domain.value_objects.agent_engine import AgentEngineType

    c = _get_container()

    try:
        engine_type = AgentEngineType(engine)
    except ValueError:
        print_error(f"Unknown engine type: {engine}")
        raise typer.Exit(code=1) from None

    caps = [cap.strip() for cap in capabilities.split(",") if cap.strip()]

    descriptor = AgentDescriptor(
        engine_type=engine_type,
        capabilities=caps,
    )
    with console.status("[blue]Registering agent...[/]"):
        _run(c.agent_registry.register(descriptor))

    console.print(f"[green]Registered:[/] {descriptor.agent_id}")
    console.print(f"Engine: {engine_type.value}")
    if caps:
        console.print(f"Capabilities: {', '.join(caps)}")

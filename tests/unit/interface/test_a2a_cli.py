"""Tests for A2A CLI commands — Sprint 19.2 (TD-120).

Uses _set_container() to inject a mock container, verifying that CLI
commands correctly call use cases and format output.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from typer.testing import CliRunner

from domain.entities.a2a import A2AConversation, A2AMessage, AgentDescriptor
from domain.value_objects.a2a import (
    A2AAction,
    A2AConversationStatus,
    A2AMessageType,
)
from domain.value_objects.agent_engine import AgentEngineType

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CLAUDE = AgentEngineType.CLAUDE_CODE
GEMINI = AgentEngineType.GEMINI_CLI


def _make_conversation(
    task_id: str = "task-1",
    participants: list[AgentEngineType] | None = None,
) -> A2AConversation:
    return A2AConversation(
        task_id=task_id,
        participants=participants or [CLAUDE, GEMINI],
    )


def _make_message(
    sender: AgentEngineType = CLAUDE,
    receiver: AgentEngineType = GEMINI,
    msg_type: A2AMessageType = A2AMessageType.REQUEST,
    action: A2AAction = A2AAction.SOLVE,
    payload: str = "test payload",
    conv_id: str = "conv-1",
    task_id: str = "task-1",
) -> A2AMessage:
    return A2AMessage(
        sender=sender,
        receiver=receiver,
        message_type=msg_type,
        action=action,
        payload=payload,
        conversation_id=conv_id,
        task_id=task_id,
    )


def _make_container(conversations: dict | None = None):
    """Build a mock container with A2A use cases and registry."""
    from application.use_cases.manage_a2a_conversation import ConversationSummary
    from application.use_cases.send_a2a_message import SendResult

    manage_uc = MagicMock()
    manage_uc.create.return_value = _make_conversation()
    manage_uc.check_expired.return_value = False
    manage_uc.check_complete.return_value = False
    manage_uc.collect_replies = AsyncMock(return_value=2)
    manage_uc.summarize.return_value = ConversationSummary(
        conversation_id="conv-1",
        task_id="task-1",
        status=A2AConversationStatus.OPEN,
        message_count=3,
        response_count=1,
        pending_count=1,
    )

    send_uc = MagicMock()
    send_uc.execute = AsyncMock(
        return_value=SendResult(
            message_id="msg-1",
            conversation_id="conv-1",
            receiver=GEMINI,
            routed=True,
        )
    )
    send_uc.reply = AsyncMock(
        return_value=SendResult(
            message_id="msg-2",
            conversation_id="conv-1",
            receiver=CLAUDE,
            routed=False,
        )
    )

    registry = MagicMock()
    registry.list_available = AsyncMock(return_value=[])
    registry.register = AsyncMock()

    container = SimpleNamespace(
        manage_a2a_conversation=manage_uc,
        send_a2a_message=send_uc,
        agent_registry=registry,
        a2a_conversations=conversations or {},
    )
    return container


def _invoke(args: list[str], container=None):
    """Invoke CLI with a mock container."""
    from interface.cli._utils import _set_container
    from interface.cli.main import app

    c = container or _make_container()
    _set_container(c)
    try:
        return runner.invoke(app, args)
    finally:
        _set_container(None)


# ===========================================================================
# TestCreate
# ===========================================================================


class TestCreate:
    def test_create_success(self) -> None:
        result = _invoke(["a2a", "create", "task-1", "-p", "claude_code,gemini_cli"])
        assert result.exit_code == 0
        assert "Created conversation" in result.output

    def test_create_invalid_engine(self) -> None:
        result = _invoke(["a2a", "create", "task-1", "-p", "invalid_engine"])
        assert result.exit_code == 1
        assert "Invalid engine type" in result.output

    def test_create_custom_ttl(self) -> None:
        result = _invoke(
            ["a2a", "create", "task-1", "-p", "claude_code,gemini_cli", "--ttl", "600"]
        )
        assert result.exit_code == 0
        assert "600s" in result.output


# ===========================================================================
# TestList
# ===========================================================================


class TestList:
    def test_list_empty(self) -> None:
        result = _invoke(["a2a", "list"])
        assert result.exit_code == 0
        assert "No conversations" in result.output

    def test_list_with_conversations(self) -> None:
        conv = _make_conversation()
        container = _make_container(conversations={conv.id: conv})
        result = _invoke(["a2a", "list"], container)
        assert result.exit_code == 0
        assert "task-1" in result.output


# ===========================================================================
# TestShow
# ===========================================================================


class TestShow:
    def test_show_not_found(self) -> None:
        result = _invoke(["a2a", "show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_show_success(self) -> None:
        conv = _make_conversation()
        container = _make_container(conversations={conv.id: conv})
        result = _invoke(["a2a", "show", conv.id], container)
        assert result.exit_code == 0
        assert "task-1" in result.output


# ===========================================================================
# TestSend
# ===========================================================================


class TestSend:
    def test_send_success(self) -> None:
        conv = _make_conversation()
        container = _make_container(conversations={conv.id: conv})
        result = _invoke(
            ["a2a", "send", conv.id, "-s", "claude_code", "-a", "solve", "-m", "do this"],
            container,
        )
        assert result.exit_code == 0
        assert "Sent" in result.output
        assert "Auto-routed" in result.output

    def test_send_not_found(self) -> None:
        result = _invoke(
            ["a2a", "send", "bad-id", "-s", "claude_code", "-a", "solve", "-m", "x"],
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_send_invalid_action(self) -> None:
        conv = _make_conversation()
        container = _make_container(conversations={conv.id: conv})
        result = _invoke(
            ["a2a", "send", conv.id, "-s", "claude_code", "-a", "bad_action", "-m", "x"],
            container,
        )
        assert result.exit_code == 1
        assert "Unknown action" in result.output

    def test_send_invalid_sender(self) -> None:
        conv = _make_conversation()
        container = _make_container(conversations={conv.id: conv})
        result = _invoke(
            ["a2a", "send", conv.id, "-s", "bad_engine", "-a", "solve", "-m", "x"],
            container,
        )
        assert result.exit_code == 1
        assert "Unknown sender" in result.output


# ===========================================================================
# TestReply
# ===========================================================================


class TestReply:
    def test_reply_success(self) -> None:
        conv = _make_conversation()
        msg = _make_message(conv_id=conv.id)
        conv.add_message(msg)
        container = _make_container(conversations={conv.id: conv})
        result = _invoke(
            ["a2a", "reply", conv.id, msg.id, "-s", "gemini_cli", "-m", "done"],
            container,
        )
        assert result.exit_code == 0
        assert "Replied" in result.output

    def test_reply_message_not_found(self) -> None:
        conv = _make_conversation()
        container = _make_container(conversations={conv.id: conv})
        result = _invoke(
            ["a2a", "reply", conv.id, "bad-msg-id", "-s", "gemini_cli", "-m", "done"],
            container,
        )
        assert result.exit_code == 1
        assert "not found" in result.output


# ===========================================================================
# TestCheck
# ===========================================================================


class TestCheck:
    def test_check_open(self) -> None:
        conv = _make_conversation()
        container = _make_container(conversations={conv.id: conv})
        result = _invoke(["a2a", "check", conv.id], container)
        assert result.exit_code == 0
        assert "still open" in result.output

    def test_check_not_found(self) -> None:
        result = _invoke(["a2a", "check", "bad-id"])
        assert result.exit_code == 1
        assert "not found" in result.output


# ===========================================================================
# TestCollect
# ===========================================================================


class TestCollect:
    def test_collect_success(self) -> None:
        conv = _make_conversation()
        container = _make_container(conversations={conv.id: conv})
        result = _invoke(["a2a", "collect", conv.id], container)
        assert result.exit_code == 0
        assert "Collected 2 new replies" in result.output

    def test_collect_not_found(self) -> None:
        result = _invoke(["a2a", "collect", "bad-id"])
        assert result.exit_code == 1


# ===========================================================================
# TestAgents
# ===========================================================================


class TestAgents:
    def test_agents_empty(self) -> None:
        result = _invoke(["a2a", "agents"])
        assert result.exit_code == 0
        assert "No agents registered" in result.output

    def test_agents_with_entries(self) -> None:
        container = _make_container()
        agent = AgentDescriptor(
            engine_type=CLAUDE,
            capabilities=["code", "review"],
        )
        container.agent_registry.list_available = AsyncMock(return_value=[agent])
        result = _invoke(["a2a", "agents"], container)
        assert result.exit_code == 0
        assert "claude_code" in result.output


# ===========================================================================
# TestRegister
# ===========================================================================


class TestRegister:
    def test_register_success(self) -> None:
        result = _invoke(
            ["a2a", "register", "-e", "claude_code", "-c", "code,review"],
        )
        assert result.exit_code == 0
        assert "Registered" in result.output

    def test_register_invalid_engine(self) -> None:
        result = _invoke(
            ["a2a", "register", "-e", "bad_engine"],
        )
        assert result.exit_code == 1
        assert "Unknown engine type" in result.output

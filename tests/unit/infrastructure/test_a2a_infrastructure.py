"""Tests for A2A infrastructure implementations (Sprint 18.3 — Phase 14.2).

Covers InMemoryA2ABroker and InMemoryAgentRegistry.
"""

from __future__ import annotations

import pytest

from domain.entities.a2a import A2AMessage, AgentDescriptor
from domain.value_objects.a2a import A2AAction, A2AMessageType
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.a2a.in_memory_agent_registry import InMemoryAgentRegistry
from infrastructure.a2a.in_memory_broker import InMemoryA2ABroker

# ===========================================================================
# Helpers
# ===========================================================================


def _msg(
    sender: AgentEngineType = AgentEngineType.CLAUDE_CODE,
    receiver: AgentEngineType | None = AgentEngineType.GEMINI_CLI,
    msg_type: A2AMessageType = A2AMessageType.REQUEST,
    action: A2AAction = A2AAction.SOLVE,
    conversation_id: str = "conv-1",
    task_id: str = "task-1",
) -> A2AMessage:
    return A2AMessage(
        sender=sender,
        receiver=receiver,
        message_type=msg_type,
        action=action,
        conversation_id=conversation_id,
        task_id=task_id,
        payload="test payload",
    )


def _descriptor(
    engine: AgentEngineType,
    caps: list[str] | None = None,
    status: str = "available",
) -> AgentDescriptor:
    return AgentDescriptor(
        engine_type=engine,
        capabilities=caps or [],
        status=status,
    )


# ===========================================================================
# InMemoryA2ABroker
# ===========================================================================


class TestInMemoryA2ABroker:
    """Tests for the in-memory A2A message broker."""

    @pytest.fixture
    def broker(self) -> InMemoryA2ABroker:
        return InMemoryA2ABroker()

    async def test_send_returns_message_id(self, broker: InMemoryA2ABroker) -> None:
        msg = _msg()
        result = await broker.send(msg)
        assert result == msg.id

    async def test_receive_gets_sent_message(self, broker: InMemoryA2ABroker) -> None:
        msg = _msg(receiver=AgentEngineType.GEMINI_CLI)
        await broker.send(msg)

        received = await broker.receive(AgentEngineType.GEMINI_CLI, timeout=1.0)
        assert received is not None
        assert received.id == msg.id

    async def test_receive_timeout_returns_none(self, broker: InMemoryA2ABroker) -> None:
        result = await broker.receive(AgentEngineType.OLLAMA, timeout=0.05)
        assert result is None

    async def test_receive_only_own_messages(self, broker: InMemoryA2ABroker) -> None:
        msg = _msg(receiver=AgentEngineType.GEMINI_CLI)
        await broker.send(msg)

        # Ollama shouldn't receive Gemini's message
        result = await broker.receive(AgentEngineType.OLLAMA, timeout=0.05)
        assert result is None

    async def test_broadcast_delivered_to_all(self, broker: InMemoryA2ABroker) -> None:
        # Pre-create inboxes by attempting (and timing out) a receive
        await broker.receive(AgentEngineType.GEMINI_CLI, timeout=0.01)
        await broker.receive(AgentEngineType.OLLAMA, timeout=0.01)

        broadcast = _msg(receiver=None)
        await broker.send(broadcast)

        gemini_msg = await broker.receive(AgentEngineType.GEMINI_CLI, timeout=1.0)
        ollama_msg = await broker.receive(AgentEngineType.OLLAMA, timeout=1.0)
        assert gemini_msg is not None
        assert ollama_msg is not None
        assert gemini_msg.id == broadcast.id
        assert ollama_msg.id == broadcast.id

    async def test_poll_replies_returns_responses(self, broker: InMemoryA2ABroker) -> None:
        conv_id = "conv-poll"
        # Send a request
        await broker.send(
            _msg(
                msg_type=A2AMessageType.REQUEST,
                conversation_id=conv_id,
            )
        )
        # Send a response
        await broker.send(
            _msg(
                sender=AgentEngineType.GEMINI_CLI,
                receiver=AgentEngineType.CLAUDE_CODE,
                msg_type=A2AMessageType.RESPONSE,
                conversation_id=conv_id,
            )
        )

        replies = await broker.poll_replies(conv_id, timeout=1.0)
        assert len(replies) == 1
        assert replies[0].message_type == A2AMessageType.RESPONSE

    async def test_poll_replies_empty_on_no_responses(self, broker: InMemoryA2ABroker) -> None:
        replies = await broker.poll_replies("nonexistent", timeout=0.05)
        assert replies == []

    async def test_poll_replies_filters_non_response(self, broker: InMemoryA2ABroker) -> None:
        conv_id = "conv-filter"
        # Only requests, no responses
        await broker.send(
            _msg(
                msg_type=A2AMessageType.REQUEST,
                conversation_id=conv_id,
            )
        )
        await broker.send(
            _msg(
                msg_type=A2AMessageType.ACK,
                conversation_id=conv_id,
            )
        )

        replies = await broker.poll_replies(conv_id, timeout=0.1)
        assert len(replies) == 0

    async def test_multiple_messages_queued(self, broker: InMemoryA2ABroker) -> None:
        receiver = AgentEngineType.GEMINI_CLI
        m1 = _msg(receiver=receiver, conversation_id="c1")
        m2 = _msg(receiver=receiver, conversation_id="c2")
        await broker.send(m1)
        await broker.send(m2)

        r1 = await broker.receive(receiver, timeout=1.0)
        r2 = await broker.receive(receiver, timeout=1.0)
        assert r1 is not None and r2 is not None
        assert {r1.id, r2.id} == {m1.id, m2.id}

    async def test_fifo_ordering(self, broker: InMemoryA2ABroker) -> None:
        receiver = AgentEngineType.OLLAMA
        msgs = []
        for i in range(5):
            m = _msg(receiver=receiver, conversation_id=f"c-{i}")
            msgs.append(m)
            await broker.send(m)

        for expected in msgs:
            got = await broker.receive(receiver, timeout=1.0)
            assert got is not None
            assert got.id == expected.id


# ===========================================================================
# InMemoryAgentRegistry
# ===========================================================================


class TestInMemoryAgentRegistry:
    """Tests for the in-memory agent registry."""

    @pytest.fixture
    def registry(self) -> InMemoryAgentRegistry:
        return InMemoryAgentRegistry()

    async def test_register_and_lookup(self, registry: InMemoryAgentRegistry) -> None:
        desc = _descriptor(AgentEngineType.CLAUDE_CODE, ["code"])
        await registry.register(desc)

        result = await registry.lookup(desc.agent_id)
        assert result is not None
        assert result.engine_type == AgentEngineType.CLAUDE_CODE

    async def test_lookup_missing_returns_none(self, registry: InMemoryAgentRegistry) -> None:
        result = await registry.lookup("nonexistent")
        assert result is None

    async def test_deregister(self, registry: InMemoryAgentRegistry) -> None:
        desc = _descriptor(AgentEngineType.OLLAMA)
        await registry.register(desc)
        await registry.deregister(desc.agent_id)

        result = await registry.lookup(desc.agent_id)
        assert result is None

    async def test_deregister_nonexistent_is_noop(self, registry: InMemoryAgentRegistry) -> None:
        # Should not raise
        await registry.deregister("does-not-exist")

    async def test_lookup_by_engine(self, registry: InMemoryAgentRegistry) -> None:
        await registry.register(_descriptor(AgentEngineType.GEMINI_CLI, ["analyze"]))
        await registry.register(_descriptor(AgentEngineType.OLLAMA, ["code"]))

        result = await registry.lookup_by_engine(AgentEngineType.GEMINI_CLI)
        assert result is not None
        assert result.engine_type == AgentEngineType.GEMINI_CLI

    async def test_lookup_by_engine_missing(self, registry: InMemoryAgentRegistry) -> None:
        result = await registry.lookup_by_engine(AgentEngineType.CLAUDE_CODE)
        assert result is None

    async def test_list_available(self, registry: InMemoryAgentRegistry) -> None:
        await registry.register(_descriptor(AgentEngineType.CLAUDE_CODE, status="available"))
        await registry.register(_descriptor(AgentEngineType.OLLAMA, status="busy"))
        await registry.register(_descriptor(AgentEngineType.GEMINI_CLI, status="available"))

        available = await registry.list_available()
        assert len(available) == 2
        engines = {d.engine_type for d in available}
        assert engines == {
            AgentEngineType.CLAUDE_CODE,
            AgentEngineType.GEMINI_CLI,
        }

    async def test_list_available_empty(self, registry: InMemoryAgentRegistry) -> None:
        available = await registry.list_available()
        assert available == []

    async def test_list_by_capability(self, registry: InMemoryAgentRegistry) -> None:
        await registry.register(_descriptor(AgentEngineType.CLAUDE_CODE, ["code", "review"]))
        await registry.register(_descriptor(AgentEngineType.GEMINI_CLI, ["analyze"]))
        await registry.register(_descriptor(AgentEngineType.OLLAMA, ["code"]))

        code_agents = await registry.list_by_capability("code")
        assert len(code_agents) == 2
        engines = {d.engine_type for d in code_agents}
        assert engines == {
            AgentEngineType.CLAUDE_CODE,
            AgentEngineType.OLLAMA,
        }

    async def test_list_by_capability_case_insensitive(
        self, registry: InMemoryAgentRegistry
    ) -> None:
        await registry.register(_descriptor(AgentEngineType.CLAUDE_CODE, ["Code"]))

        result = await registry.list_by_capability("code")
        assert len(result) == 1

    async def test_register_updates_existing(self, registry: InMemoryAgentRegistry) -> None:
        desc = _descriptor(AgentEngineType.OLLAMA, ["code"])
        await registry.register(desc)

        # Update with same agent_id but new capabilities
        updated = AgentDescriptor(
            agent_id=desc.agent_id,
            engine_type=AgentEngineType.OLLAMA,
            capabilities=["code", "review"],
        )
        await registry.register(updated)

        result = await registry.lookup(desc.agent_id)
        assert result is not None
        assert len(result.capabilities) == 2

    async def test_list_by_capability_no_match(self, registry: InMemoryAgentRegistry) -> None:
        await registry.register(_descriptor(AgentEngineType.CLAUDE_CODE, ["code"]))

        result = await registry.list_by_capability("review")
        assert result == []

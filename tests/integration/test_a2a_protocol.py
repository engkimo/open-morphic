"""A2A Protocol integration tests — Sprint 18.6 (Phase 14.5).

Tests the full A2A pipeline: register agents → create conversation →
send message (with auto-routing) → reply → check complete → summarize.
Uses real InMemory implementations, no mocks.

Run:
    uv run pytest tests/integration/test_a2a_protocol.py -v -s
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from application.use_cases.manage_a2a_conversation import (
    ManageA2AConversationUseCase,
)
from application.use_cases.send_a2a_message import SendA2AMessageUseCase
from domain.entities.a2a import AgentDescriptor
from domain.services.a2a_conversation_manager import A2AConversationManager
from domain.value_objects.a2a import A2AAction, A2AConversationStatus, A2AMessageType
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.a2a.in_memory_agent_registry import InMemoryAgentRegistry
from infrastructure.a2a.in_memory_broker import InMemoryA2ABroker


@pytest.fixture
def broker() -> InMemoryA2ABroker:
    return InMemoryA2ABroker()


@pytest.fixture
def registry() -> InMemoryAgentRegistry:
    return InMemoryAgentRegistry()


@pytest.fixture
def send_uc(broker: InMemoryA2ABroker, registry: InMemoryAgentRegistry) -> SendA2AMessageUseCase:
    return SendA2AMessageUseCase(broker=broker, registry=registry)


@pytest.fixture
def manage_uc(broker: InMemoryA2ABroker) -> ManageA2AConversationUseCase:
    return ManageA2AConversationUseCase(broker=broker)


# ===========================================================================
# Test 1: Full conversation lifecycle
# ===========================================================================


async def test_full_conversation_lifecycle(
    send_uc: SendA2AMessageUseCase,
    manage_uc: ManageA2AConversationUseCase,
) -> None:
    """Create → send → reply → check complete → summarize."""
    conv = manage_uc.create(
        task_id="lifecycle-1",
        participants=[AgentEngineType.CLAUDE_CODE, AgentEngineType.GEMINI_CLI],
    )
    assert conv.is_open

    # Claude sends request to Gemini
    send_result = await send_uc.execute(
        sender=AgentEngineType.CLAUDE_CODE,
        action=A2AAction.SOLVE,
        conversation=conv,
        payload="implement auth module",
        receiver=AgentEngineType.GEMINI_CLI,
    )
    assert send_result.routed is False
    assert send_result.receiver == AgentEngineType.GEMINI_CLI
    assert conv.message_count == 1

    # Gemini replies
    request_msg = conv.messages[0]
    reply_result = await send_uc.reply(
        sender=AgentEngineType.GEMINI_CLI,
        request=request_msg,
        conversation=conv,
        payload="auth module implemented",
        artifacts={"code": "def auth(): pass"},
    )
    assert reply_result.receiver == AgentEngineType.CLAUDE_CODE
    assert conv.message_count == 2

    # Check complete — should auto-resolve
    complete = manage_uc.check_complete(conv)
    assert complete is True
    assert conv.status == A2AConversationStatus.RESOLVED

    # Summarize
    summary = manage_uc.summarize(conv)
    assert summary.message_count == 2
    assert summary.response_count == 1
    assert summary.pending_count == 0
    assert summary.status == A2AConversationStatus.RESOLVED


# ===========================================================================
# Test 2: Auto-routing with registered agents
# ===========================================================================


async def test_auto_routing_with_registry(
    send_uc: SendA2AMessageUseCase,
    manage_uc: ManageA2AConversationUseCase,
    registry: InMemoryAgentRegistry,
) -> None:
    """Register agents → send without receiver → auto-route based on capability."""
    # Register agents with capabilities
    await registry.register(
        AgentDescriptor(
            engine_type=AgentEngineType.GEMINI_CLI,
            capabilities=["code", "review"],
        )
    )
    await registry.register(
        AgentDescriptor(
            engine_type=AgentEngineType.OLLAMA,
            capabilities=["draft", "summarize"],
        )
    )

    conv = manage_uc.create(
        task_id="route-1",
        participants=[
            AgentEngineType.CLAUDE_CODE,
            AgentEngineType.GEMINI_CLI,
            AgentEngineType.OLLAMA,
        ],
    )

    # Send without explicit receiver — should auto-route to Gemini (has "code" capability)
    result = await send_uc.execute(
        sender=AgentEngineType.CLAUDE_CODE,
        action=A2AAction.SOLVE,
        conversation=conv,
        payload="write unit tests",
    )
    assert result.routed is True
    assert result.receiver == AgentEngineType.GEMINI_CLI


# ===========================================================================
# Test 3: Broker message delivery
# ===========================================================================


async def test_broker_delivery_and_collection(
    send_uc: SendA2AMessageUseCase,
    manage_uc: ManageA2AConversationUseCase,
    broker: InMemoryA2ABroker,
) -> None:
    """Messages sent via use case are deliverable via broker.receive()."""
    conv = manage_uc.create(
        task_id="delivery-1",
        participants=[AgentEngineType.CLAUDE_CODE, AgentEngineType.GEMINI_CLI],
    )

    await send_uc.execute(
        sender=AgentEngineType.CLAUDE_CODE,
        action=A2AAction.REVIEW,
        conversation=conv,
        payload="review this PR",
        receiver=AgentEngineType.GEMINI_CLI,
    )

    # Gemini can receive the message from broker
    received = await broker.receive(AgentEngineType.GEMINI_CLI, timeout=1.0)
    assert received is not None
    assert received.payload == "review this PR"
    assert received.action == A2AAction.REVIEW
    assert received.sender == AgentEngineType.CLAUDE_CODE


# ===========================================================================
# Test 4: Reply collection via broker polling
# ===========================================================================


async def test_collect_replies_via_broker(
    send_uc: SendA2AMessageUseCase,
    manage_uc: ManageA2AConversationUseCase,
    broker: InMemoryA2ABroker,
) -> None:
    """Simulate external reply via broker → collect_replies picks it up."""
    conv = manage_uc.create(
        task_id="collect-1",
        participants=[AgentEngineType.CLAUDE_CODE, AgentEngineType.GEMINI_CLI],
    )

    # Claude sends request
    await send_uc.execute(
        sender=AgentEngineType.CLAUDE_CODE,
        action=A2AAction.SOLVE,
        conversation=conv,
        payload="fix bug",
        receiver=AgentEngineType.GEMINI_CLI,
    )

    # Simulate Gemini's response directly via broker (external agent)
    request_msg = conv.messages[0]
    response_msg = A2AConversationManager.create_response(
        sender=AgentEngineType.GEMINI_CLI,
        request=request_msg,
        payload="bug fixed",
    )
    await broker.send(response_msg)

    # Collect replies
    new_count = await manage_uc.collect_replies(conv, timeout=1.0)
    assert new_count == 1
    assert conv.message_count == 2

    # Check complete after collection
    assert manage_uc.check_complete(conv) is True
    assert conv.status == A2AConversationStatus.RESOLVED


# ===========================================================================
# Test 5: TTL expiration
# ===========================================================================


async def test_conversation_ttl_expiration(
    manage_uc: ManageA2AConversationUseCase,
) -> None:
    """Conversation expires after TTL."""
    conv = manage_uc.create(
        task_id="ttl-1",
        participants=[AgentEngineType.CLAUDE_CODE, AgentEngineType.OLLAMA],
        ttl_seconds=5,
    )
    assert conv.is_open

    # Simulate time passing beyond TTL
    future = conv.created_at + timedelta(seconds=6)
    expired = manage_uc.check_expired(conv, now=future)
    assert expired is True
    assert conv.status == A2AConversationStatus.TIMEOUT


# ===========================================================================
# Test 6: Multi-party conversation
# ===========================================================================


async def test_multi_party_conversation(
    send_uc: SendA2AMessageUseCase,
    manage_uc: ManageA2AConversationUseCase,
) -> None:
    """Three agents: Claude sends, Gemini + Ollama respond."""
    conv = manage_uc.create(
        task_id="multi-1",
        participants=[
            AgentEngineType.CLAUDE_CODE,
            AgentEngineType.GEMINI_CLI,
            AgentEngineType.OLLAMA,
        ],
    )

    # Claude sends to Gemini
    await send_uc.execute(
        sender=AgentEngineType.CLAUDE_CODE,
        action=A2AAction.SOLVE,
        conversation=conv,
        payload="implement feature",
        receiver=AgentEngineType.GEMINI_CLI,
    )

    # Claude also sends to Ollama
    await send_uc.execute(
        sender=AgentEngineType.CLAUDE_CODE,
        action=A2AAction.REVIEW,
        conversation=conv,
        payload="review feature",
        receiver=AgentEngineType.OLLAMA,
    )

    # Both respond
    for msg in conv.messages:
        if msg.receiver == AgentEngineType.GEMINI_CLI:
            await send_uc.reply(
                sender=AgentEngineType.GEMINI_CLI,
                request=msg,
                conversation=conv,
                payload="feature done",
            )
        elif msg.receiver == AgentEngineType.OLLAMA:
            await send_uc.reply(
                sender=AgentEngineType.OLLAMA,
                request=msg,
                conversation=conv,
                payload="review looks good",
            )

    assert conv.message_count == 4
    assert manage_uc.check_complete(conv) is True
    assert conv.status == A2AConversationStatus.RESOLVED

    summary = manage_uc.summarize(conv)
    assert summary.response_count == 2
    assert summary.pending_count == 0


# ===========================================================================
# Test 7: Multiple independent conversations
# ===========================================================================


async def test_multiple_independent_conversations(
    send_uc: SendA2AMessageUseCase,
    manage_uc: ManageA2AConversationUseCase,
) -> None:
    """Two separate conversations don't interfere with each other."""
    conv_a = manage_uc.create(
        task_id="conv-a",
        participants=[AgentEngineType.CLAUDE_CODE, AgentEngineType.GEMINI_CLI],
    )
    conv_b = manage_uc.create(
        task_id="conv-b",
        participants=[AgentEngineType.CLAUDE_CODE, AgentEngineType.OLLAMA],
    )

    # Send in both conversations
    await send_uc.execute(
        sender=AgentEngineType.CLAUDE_CODE,
        action=A2AAction.SOLVE,
        conversation=conv_a,
        payload="task A",
        receiver=AgentEngineType.GEMINI_CLI,
    )
    await send_uc.execute(
        sender=AgentEngineType.CLAUDE_CODE,
        action=A2AAction.SOLVE,
        conversation=conv_b,
        payload="task B",
        receiver=AgentEngineType.OLLAMA,
    )

    # Reply only in conv_a
    await send_uc.reply(
        sender=AgentEngineType.GEMINI_CLI,
        request=conv_a.messages[0],
        conversation=conv_a,
        payload="A done",
    )

    # conv_a should be resolvable, conv_b should not
    assert manage_uc.check_complete(conv_a) is True
    assert manage_uc.check_complete(conv_b) is False
    assert conv_a.status == A2AConversationStatus.RESOLVED
    assert conv_b.status == A2AConversationStatus.OPEN


# ===========================================================================
# Test 8: Agent registry lifecycle
# ===========================================================================


async def test_agent_registry_lifecycle(
    registry: InMemoryAgentRegistry,
) -> None:
    """Register → list → lookup → deregister → verify gone."""
    desc = AgentDescriptor(
        engine_type=AgentEngineType.CLAUDE_CODE,
        capabilities=["code", "architecture"],
    )
    await registry.register(desc)

    # List available
    available = await registry.list_available()
    assert len(available) == 1
    assert available[0].engine_type == AgentEngineType.CLAUDE_CODE

    # Lookup by engine
    found = await registry.lookup_by_engine(AgentEngineType.CLAUDE_CODE)
    assert found is not None
    assert found.has_capability("code")
    assert found.has_capability("ARCHITECTURE")  # case-insensitive

    # List by capability
    code_agents = await registry.list_by_capability("code")
    assert len(code_agents) == 1

    # Deregister
    await registry.deregister(desc.agent_id)
    available = await registry.list_available()
    assert len(available) == 0


# ===========================================================================
# Test 9: Message artifacts preserved through pipeline
# ===========================================================================


async def test_artifacts_preserved(
    send_uc: SendA2AMessageUseCase,
    manage_uc: ManageA2AConversationUseCase,
) -> None:
    """Artifacts survive the full send → receive → reply pipeline."""
    conv = manage_uc.create(
        task_id="artifacts-1",
        participants=[AgentEngineType.CLAUDE_CODE, AgentEngineType.GEMINI_CLI],
    )

    await send_uc.execute(
        sender=AgentEngineType.CLAUDE_CODE,
        action=A2AAction.REVIEW,
        conversation=conv,
        payload="review this diff",
        receiver=AgentEngineType.GEMINI_CLI,
        artifacts={"diff": "--- a/main.py\n+++ b/main.py"},
    )

    req = conv.messages[0]
    assert req.artifacts["diff"].startswith("---")

    await send_uc.reply(
        sender=AgentEngineType.GEMINI_CLI,
        request=req,
        conversation=conv,
        payload="LGTM",
        artifacts={"review_score": "9/10"},
    )

    resp = conv.messages[1]
    assert resp.artifacts["review_score"] == "9/10"
    assert resp.message_type == A2AMessageType.RESPONSE
    assert resp.reply_to == req.id


# ===========================================================================
# Test 10: Full API E2E via TestClient
# ===========================================================================


async def test_api_e2e_flow() -> None:
    """Full E2E through FastAPI routes: register → create → send → reply → check."""
    from fastapi.testclient import TestClient

    from domain.entities.a2a import A2AConversation
    from interface.api.main import create_app

    class TestContainer:
        def __init__(self) -> None:
            self.a2a_broker = InMemoryA2ABroker()
            self.agent_registry = InMemoryAgentRegistry()
            self.send_a2a_message = SendA2AMessageUseCase(
                broker=self.a2a_broker,
                registry=self.agent_registry,
            )
            self.manage_a2a_conversation = ManageA2AConversationUseCase(
                broker=self.a2a_broker,
            )
            self.a2a_conversations: dict[str, A2AConversation] = {}

    app = create_app(container=TestContainer())
    client = TestClient(app)

    # 1. Register agents
    client.post(
        "/api/a2a/agents",
        json={"engine_type": "claude_code", "capabilities": ["code"]},
    )
    client.post(
        "/api/a2a/agents",
        json={"engine_type": "gemini_cli", "capabilities": ["review"]},
    )
    agents_resp = client.get("/api/a2a/agents")
    assert agents_resp.json()["count"] == 2

    # 2. Create conversation
    conv_resp = client.post(
        "/api/a2a/conversations",
        json={
            "task_id": "e2e-1",
            "participants": ["claude_code", "gemini_cli"],
        },
    )
    assert conv_resp.status_code == 201
    conv_id = conv_resp.json()["id"]

    # 3. Send message
    send_resp = client.post(
        f"/api/a2a/conversations/{conv_id}/messages",
        json={
            "sender": "claude_code",
            "action": "solve",
            "payload": "implement feature X",
            "receiver": "gemini_cli",
        },
    )
    assert send_resp.status_code == 201
    msg_id = send_resp.json()["message_id"]

    # 4. Reply
    reply_resp = client.post(
        f"/api/a2a/conversations/{conv_id}/reply",
        json={
            "sender": "gemini_cli",
            "message_id": msg_id,
            "payload": "feature X done",
        },
    )
    assert reply_resp.status_code == 201
    assert reply_resp.json()["receiver"] == "claude_code"

    # 5. Check complete
    check_resp = client.post(f"/api/a2a/conversations/{conv_id}/check")
    assert check_resp.status_code == 200
    assert check_resp.json()["complete"] is True
    assert check_resp.json()["status"] == "resolved"

    # 6. Get final state
    get_resp = client.get(f"/api/a2a/conversations/{conv_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["status"] == "resolved"
    assert data["message_count"] == 2
    assert len(data["messages"]) == 2
    assert data["messages"][0]["sender"] == "claude_code"
    assert data["messages"][1]["sender"] == "gemini_cli"

"""Tests for A2A Protocol API routes (Sprint 18.5 — Phase 14.4)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from domain.entities.a2a import A2AConversation, AgentDescriptor
from domain.value_objects.agent_engine import AgentEngineType


def _make_app():  # type: ignore[no-untyped-def]
    """Create a test app with minimal A2A container."""
    from application.use_cases.manage_a2a_conversation import (
        ManageA2AConversationUseCase,
    )
    from application.use_cases.send_a2a_message import SendA2AMessageUseCase
    from infrastructure.a2a.in_memory_agent_registry import InMemoryAgentRegistry
    from infrastructure.a2a.in_memory_broker import InMemoryA2ABroker
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

    container = TestContainer()
    app = create_app(container=container)
    return app, container


# ===========================================================================
# Conversations
# ===========================================================================


class TestConversationAPI:
    def setup_method(self) -> None:
        self.app, self.container = _make_app()
        self.client = TestClient(self.app)

    def test_create_conversation(self) -> None:
        resp = self.client.post(
            "/api/a2a/conversations",
            json={
                "task_id": "t-1",
                "participants": ["claude_code", "gemini_cli"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["task_id"] == "t-1"
        assert data["status"] == "open"
        assert data["message_count"] == 0
        assert len(data["participants"]) == 2
        assert data["pending_count"] == 2
        # Conversation tracked in container
        assert data["id"] in self.container.a2a_conversations

    def test_create_conversation_custom_ttl(self) -> None:
        resp = self.client.post(
            "/api/a2a/conversations",
            json={
                "task_id": "t-2",
                "participants": ["ollama"],
                "ttl_seconds": 60,
            },
        )
        assert resp.status_code == 201

    def test_create_conversation_invalid_engine(self) -> None:
        resp = self.client.post(
            "/api/a2a/conversations",
            json={
                "task_id": "t-1",
                "participants": ["invalid_engine"],
            },
        )
        assert resp.status_code == 400

    def test_create_conversation_empty_participants(self) -> None:
        resp = self.client.post(
            "/api/a2a/conversations",
            json={
                "task_id": "t-1",
                "participants": [],
            },
        )
        assert resp.status_code == 422

    def test_get_conversation(self) -> None:
        # Create first
        create_resp = self.client.post(
            "/api/a2a/conversations",
            json={
                "task_id": "t-1",
                "participants": ["claude_code", "gemini_cli"],
            },
        )
        conv_id = create_resp.json()["id"]

        resp = self.client.get(f"/api/a2a/conversations/{conv_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == conv_id
        assert data["task_id"] == "t-1"

    def test_get_conversation_not_found(self) -> None:
        resp = self.client.get("/api/a2a/conversations/nonexistent")
        assert resp.status_code == 404

    def test_check_conversation_not_expired(self) -> None:
        create_resp = self.client.post(
            "/api/a2a/conversations",
            json={
                "task_id": "t-1",
                "participants": ["claude_code"],
                "ttl_seconds": 300,
            },
        )
        conv_id = create_resp.json()["id"]

        resp = self.client.post(f"/api/a2a/conversations/{conv_id}/check")
        assert resp.status_code == 200
        data = resp.json()
        assert data["expired"] is False
        assert data["complete"] is False
        assert data["status"] == "open"

    def test_check_conversation_not_found(self) -> None:
        resp = self.client.post("/api/a2a/conversations/nonexistent/check")
        assert resp.status_code == 404

    def test_collect_replies(self) -> None:
        create_resp = self.client.post(
            "/api/a2a/conversations",
            json={
                "task_id": "t-1",
                "participants": ["claude_code", "gemini_cli"],
            },
        )
        conv_id = create_resp.json()["id"]

        resp = self.client.post(f"/api/a2a/conversations/{conv_id}/collect")
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_replies"] == 0
        assert data["total_messages"] == 0

    def test_collect_replies_not_found(self) -> None:
        resp = self.client.post("/api/a2a/conversations/nonexistent/collect")
        assert resp.status_code == 404


# ===========================================================================
# Messages
# ===========================================================================


class TestMessageAPI:
    def setup_method(self) -> None:
        self.app, self.container = _make_app()
        self.client = TestClient(self.app)

    def _create_conversation(self) -> str:
        resp = self.client.post(
            "/api/a2a/conversations",
            json={
                "task_id": "t-1",
                "participants": ["claude_code", "gemini_cli"],
            },
        )
        return resp.json()["id"]

    def test_send_message(self) -> None:
        conv_id = self._create_conversation()
        resp = self.client.post(
            f"/api/a2a/conversations/{conv_id}/messages",
            json={
                "sender": "claude_code",
                "action": "solve",
                "payload": "implement auth",
                "receiver": "gemini_cli",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["conversation_id"] == conv_id
        assert data["receiver"] == "gemini_cli"
        assert data["routed"] is False

    @pytest.mark.asyncio
    async def test_send_message_auto_route(self) -> None:
        await self.container.agent_registry.register(
            AgentDescriptor(
                engine_type=AgentEngineType.GEMINI_CLI,
                capabilities=["code"],
            )
        )
        conv_id = self._create_conversation()
        resp = self.client.post(
            f"/api/a2a/conversations/{conv_id}/messages",
            json={
                "sender": "claude_code",
                "action": "solve",
                "payload": "implement auth",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["routed"] is True
        assert data["receiver"] == "gemini_cli"

    def test_send_message_with_artifacts(self) -> None:
        conv_id = self._create_conversation()
        resp = self.client.post(
            f"/api/a2a/conversations/{conv_id}/messages",
            json={
                "sender": "claude_code",
                "action": "inform",
                "payload": "review result",
                "artifacts": {"diff": "--- a/foo.py"},
            },
        )
        assert resp.status_code == 201

    def test_send_message_invalid_action(self) -> None:
        conv_id = self._create_conversation()
        resp = self.client.post(
            f"/api/a2a/conversations/{conv_id}/messages",
            json={
                "sender": "claude_code",
                "action": "invalid_action",
                "payload": "test",
            },
        )
        assert resp.status_code == 400

    def test_send_message_invalid_sender(self) -> None:
        conv_id = self._create_conversation()
        resp = self.client.post(
            f"/api/a2a/conversations/{conv_id}/messages",
            json={
                "sender": "invalid",
                "action": "solve",
                "payload": "test",
            },
        )
        assert resp.status_code == 400

    def test_send_message_conversation_not_found(self) -> None:
        resp = self.client.post(
            "/api/a2a/conversations/nonexistent/messages",
            json={
                "sender": "claude_code",
                "action": "solve",
                "payload": "test",
            },
        )
        assert resp.status_code == 404

    def test_reply_message(self) -> None:
        conv_id = self._create_conversation()
        # Send initial message
        send_resp = self.client.post(
            f"/api/a2a/conversations/{conv_id}/messages",
            json={
                "sender": "claude_code",
                "action": "solve",
                "payload": "implement auth",
                "receiver": "gemini_cli",
            },
        )
        msg_id = send_resp.json()["message_id"]

        # Reply
        resp = self.client.post(
            f"/api/a2a/conversations/{conv_id}/reply",
            json={
                "sender": "gemini_cli",
                "message_id": msg_id,
                "payload": "done",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["receiver"] == "claude_code"
        assert data["routed"] is False

    def test_reply_message_not_found(self) -> None:
        conv_id = self._create_conversation()
        resp = self.client.post(
            f"/api/a2a/conversations/{conv_id}/reply",
            json={
                "sender": "gemini_cli",
                "message_id": "nonexistent-msg",
                "payload": "done",
            },
        )
        assert resp.status_code == 404

    def test_reply_conversation_not_found(self) -> None:
        resp = self.client.post(
            "/api/a2a/conversations/nonexistent/reply",
            json={
                "sender": "gemini_cli",
                "message_id": "msg-1",
                "payload": "done",
            },
        )
        assert resp.status_code == 404

    def test_full_conversation_flow(self) -> None:
        """End-to-end: create → send → reply → check complete → get summary."""
        conv_id = self._create_conversation()

        # Send request
        send_resp = self.client.post(
            f"/api/a2a/conversations/{conv_id}/messages",
            json={
                "sender": "claude_code",
                "action": "solve",
                "payload": "implement auth",
                "receiver": "gemini_cli",
            },
        )
        msg_id = send_resp.json()["message_id"]

        # Reply
        self.client.post(
            f"/api/a2a/conversations/{conv_id}/reply",
            json={
                "sender": "gemini_cli",
                "message_id": msg_id,
                "payload": "done",
            },
        )

        # Check complete
        check_resp = self.client.post(f"/api/a2a/conversations/{conv_id}/check")
        data = check_resp.json()
        assert data["complete"] is True
        assert data["status"] == "resolved"

        # Get final state
        get_resp = self.client.get(f"/api/a2a/conversations/{conv_id}")
        summary = get_resp.json()
        assert summary["status"] == "resolved"
        assert summary["message_count"] == 2
        assert summary["response_count"] == 1
        assert len(summary["messages"]) == 2


# ===========================================================================
# Agent Registry
# ===========================================================================


class TestAgentRegistryAPI:
    def setup_method(self) -> None:
        self.app, self.container = _make_app()
        self.client = TestClient(self.app)

    def test_list_agents_empty(self) -> None:
        resp = self.client.get("/api/a2a/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["agents"] == []

    def test_register_agent(self) -> None:
        resp = self.client.post(
            "/api/a2a/agents",
            json={
                "engine_type": "claude_code",
                "capabilities": ["code", "review"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["engine_type"] == "claude_code"
        assert data["capabilities"] == ["code", "review"]
        assert data["status"] == "available"

    def test_register_agent_invalid_engine(self) -> None:
        resp = self.client.post(
            "/api/a2a/agents",
            json={
                "engine_type": "invalid",
                "capabilities": [],
            },
        )
        assert resp.status_code == 400

    def test_register_and_list(self) -> None:
        self.client.post(
            "/api/a2a/agents",
            json={"engine_type": "claude_code", "capabilities": ["code"]},
        )
        self.client.post(
            "/api/a2a/agents",
            json={"engine_type": "gemini_cli", "capabilities": ["review"]},
        )
        resp = self.client.get("/api/a2a/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2

    def test_deregister_agent(self) -> None:
        # Register first
        reg_resp = self.client.post(
            "/api/a2a/agents",
            json={"engine_type": "ollama", "capabilities": ["draft"]},
        )
        agent_id = reg_resp.json()["agent_id"]

        # Deregister
        resp = self.client.delete(f"/api/a2a/agents/{agent_id}")
        assert resp.status_code == 204

        # Verify gone
        list_resp = self.client.get("/api/a2a/agents")
        assert list_resp.json()["count"] == 0

    def test_deregister_unknown_agent(self) -> None:
        # Should not error (no-op for unknown IDs)
        resp = self.client.delete("/api/a2a/agents/unknown-id")
        assert resp.status_code == 204

    def test_register_missing_engine(self) -> None:
        resp = self.client.post("/api/a2a/agents", json={})
        assert resp.status_code == 422

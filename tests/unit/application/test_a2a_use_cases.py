"""Tests for A2A use cases (Sprint 18.4 — Phase 14.3).

Covers SendA2AMessageUseCase and ManageA2AConversationUseCase.
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
from domain.value_objects.a2a import (
    A2AAction,
    A2AConversationStatus,
    A2AMessageType,
)
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.a2a.in_memory_agent_registry import InMemoryAgentRegistry
from infrastructure.a2a.in_memory_broker import InMemoryA2ABroker

# ===========================================================================
# Helpers
# ===========================================================================


def _descriptor(
    engine: AgentEngineType,
    caps: list[str] | None = None,
) -> AgentDescriptor:
    return AgentDescriptor(
        engine_type=engine,
        capabilities=caps or ["code"],
    )


# ===========================================================================
# SendA2AMessageUseCase
# ===========================================================================


class TestSendA2AMessageUseCase:
    @pytest.fixture
    def broker(self) -> InMemoryA2ABroker:
        return InMemoryA2ABroker()

    @pytest.fixture
    def registry(self) -> InMemoryAgentRegistry:
        return InMemoryAgentRegistry()

    @pytest.fixture
    def use_case(
        self,
        broker: InMemoryA2ABroker,
        registry: InMemoryAgentRegistry,
    ) -> SendA2AMessageUseCase:
        return SendA2AMessageUseCase(broker=broker, registry=registry)

    async def test_send_with_explicit_receiver(
        self,
        use_case: SendA2AMessageUseCase,
    ) -> None:
        conv = A2AConversationManager.create_conversation(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
            ],
        )
        result = await use_case.execute(
            sender=AgentEngineType.CLAUDE_CODE,
            action=A2AAction.SOLVE,
            conversation=conv,
            payload="implement auth",
            receiver=AgentEngineType.GEMINI_CLI,
        )
        assert result.receiver == AgentEngineType.GEMINI_CLI
        assert result.routed is False
        assert conv.message_count == 1

    async def test_send_auto_routes(
        self,
        use_case: SendA2AMessageUseCase,
        registry: InMemoryAgentRegistry,
    ) -> None:
        # Register Gemini with "code" capability
        await registry.register(_descriptor(AgentEngineType.GEMINI_CLI, ["code"]))
        conv = A2AConversationManager.create_conversation(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
            ],
        )
        result = await use_case.execute(
            sender=AgentEngineType.CLAUDE_CODE,
            action=A2AAction.SOLVE,
            conversation=conv,
            payload="implement auth",
        )
        assert result.routed is True
        assert result.receiver == AgentEngineType.GEMINI_CLI

    async def test_send_no_available_receiver(
        self,
        use_case: SendA2AMessageUseCase,
    ) -> None:
        conv = A2AConversationManager.create_conversation(
            task_id="t1",
            participants=[AgentEngineType.CLAUDE_CODE],
        )
        result = await use_case.execute(
            sender=AgentEngineType.CLAUDE_CODE,
            action=A2AAction.SOLVE,
            conversation=conv,
            payload="help",
        )
        # No agents registered → receiver is None (broadcast)
        assert result.receiver is None
        assert result.routed is False

    async def test_reply(
        self,
        use_case: SendA2AMessageUseCase,
    ) -> None:
        conv = A2AConversationManager.create_conversation(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
            ],
        )
        # First send a request
        await use_case.execute(
            sender=AgentEngineType.CLAUDE_CODE,
            action=A2AAction.SOLVE,
            conversation=conv,
            payload="implement auth",
            receiver=AgentEngineType.GEMINI_CLI,
        )

        # Then reply
        request_msg = conv.messages[0]
        reply_result = await use_case.reply(
            sender=AgentEngineType.GEMINI_CLI,
            request=request_msg,
            conversation=conv,
            payload="done",
        )
        assert reply_result.receiver == AgentEngineType.CLAUDE_CODE
        assert reply_result.routed is False
        assert conv.message_count == 2
        resp_msg = conv.messages[1]
        assert resp_msg.message_type == A2AMessageType.RESPONSE
        assert resp_msg.reply_to == request_msg.id

    async def test_send_with_artifacts(
        self,
        use_case: SendA2AMessageUseCase,
    ) -> None:
        conv = A2AConversationManager.create_conversation(
            task_id="t1",
            participants=[AgentEngineType.CLAUDE_CODE],
        )
        await use_case.execute(
            sender=AgentEngineType.CLAUDE_CODE,
            action=A2AAction.INFORM,
            conversation=conv,
            payload="code review result",
            artifacts={"diff": "--- a/foo.py\n+++ b/foo.py"},
        )
        msg = conv.messages[0]
        assert msg.artifacts["diff"].startswith("---")

    async def test_message_delivered_to_broker(
        self,
        use_case: SendA2AMessageUseCase,
        broker: InMemoryA2ABroker,
    ) -> None:
        conv = A2AConversationManager.create_conversation(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
            ],
        )
        await use_case.execute(
            sender=AgentEngineType.CLAUDE_CODE,
            action=A2AAction.SOLVE,
            conversation=conv,
            payload="test",
            receiver=AgentEngineType.GEMINI_CLI,
        )
        received = await broker.receive(AgentEngineType.GEMINI_CLI, timeout=1.0)
        assert received is not None
        assert received.payload == "test"


# ===========================================================================
# ManageA2AConversationUseCase
# ===========================================================================


class TestManageA2AConversationUseCase:
    @pytest.fixture
    def broker(self) -> InMemoryA2ABroker:
        return InMemoryA2ABroker()

    @pytest.fixture
    def use_case(self, broker: InMemoryA2ABroker) -> ManageA2AConversationUseCase:
        return ManageA2AConversationUseCase(broker=broker)

    def test_create(self, use_case: ManageA2AConversationUseCase) -> None:
        conv = use_case.create(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
            ],
        )
        assert conv.is_open
        assert conv.task_id == "t1"
        assert len(conv.participants) == 2

    def test_create_custom_ttl(self, use_case: ManageA2AConversationUseCase) -> None:
        conv = use_case.create(
            task_id="t1",
            participants=[AgentEngineType.OLLAMA],
            ttl_seconds=60,
        )
        assert conv.ttl_seconds == 60

    def test_check_expired_marks_timeout(self, use_case: ManageA2AConversationUseCase) -> None:
        conv = use_case.create(
            task_id="t1",
            participants=[AgentEngineType.OLLAMA],
            ttl_seconds=10,
        )
        future = conv.created_at + timedelta(seconds=11)
        expired = use_case.check_expired(conv, now=future)
        assert expired is True
        assert conv.status == A2AConversationStatus.TIMEOUT

    def test_check_expired_not_expired(self, use_case: ManageA2AConversationUseCase) -> None:
        conv = use_case.create(
            task_id="t1",
            participants=[AgentEngineType.OLLAMA],
            ttl_seconds=300,
        )
        near = conv.created_at + timedelta(seconds=5)
        expired = use_case.check_expired(conv, now=near)
        assert expired is False
        assert conv.is_open

    def test_check_expired_skips_closed(self, use_case: ManageA2AConversationUseCase) -> None:
        conv = use_case.create(
            task_id="t1",
            participants=[AgentEngineType.OLLAMA],
            ttl_seconds=1,
        )
        conv.resolve()
        future = conv.created_at + timedelta(seconds=100)
        # Already resolved — should not mark timeout
        expired = use_case.check_expired(conv, now=future)
        assert expired is False
        assert conv.status == A2AConversationStatus.RESOLVED

    def test_check_complete_resolves(self, use_case: ManageA2AConversationUseCase) -> None:
        conv = use_case.create(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
            ],
        )
        # Claude sends request
        req = A2AConversationManager.create_request(
            sender=AgentEngineType.CLAUDE_CODE,
            receiver=AgentEngineType.GEMINI_CLI,
            conversation_id=conv.id,
            task_id="t1",
            action=A2AAction.SOLVE,
            payload="do it",
        )
        conv.add_message(req)

        # Gemini responds
        resp = A2AConversationManager.create_response(
            sender=AgentEngineType.GEMINI_CLI,
            request=req,
            payload="done",
        )
        conv.add_message(resp)

        complete = use_case.check_complete(conv)
        assert complete is True
        assert conv.status == A2AConversationStatus.RESOLVED

    def test_check_complete_not_yet(self, use_case: ManageA2AConversationUseCase) -> None:
        conv = use_case.create(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
                AgentEngineType.OLLAMA,
            ],
        )
        req = A2AConversationManager.create_request(
            sender=AgentEngineType.CLAUDE_CODE,
            receiver=AgentEngineType.GEMINI_CLI,
            conversation_id=conv.id,
            task_id="t1",
            action=A2AAction.SOLVE,
            payload="do it",
        )
        conv.add_message(req)

        # Only Gemini responds, Ollama hasn't yet
        resp = A2AConversationManager.create_response(
            sender=AgentEngineType.GEMINI_CLI,
            request=req,
            payload="done",
        )
        conv.add_message(resp)

        complete = use_case.check_complete(conv)
        assert complete is False
        assert conv.is_open

    async def test_collect_replies(
        self,
        use_case: ManageA2AConversationUseCase,
        broker: InMemoryA2ABroker,
    ) -> None:
        conv = use_case.create(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
            ],
        )
        req = A2AConversationManager.create_request(
            sender=AgentEngineType.CLAUDE_CODE,
            receiver=AgentEngineType.GEMINI_CLI,
            conversation_id=conv.id,
            task_id="t1",
            action=A2AAction.SOLVE,
            payload="do it",
        )
        conv.add_message(req)

        # Gemini sends response via broker
        resp = A2AConversationManager.create_response(
            sender=AgentEngineType.GEMINI_CLI,
            request=req,
            payload="done",
        )
        await broker.send(resp)

        count = await use_case.collect_replies(conv, timeout=1.0)
        assert count == 1
        assert conv.message_count == 2  # req + collected resp

    async def test_collect_replies_no_duplicates(
        self,
        use_case: ManageA2AConversationUseCase,
        broker: InMemoryA2ABroker,
    ) -> None:
        conv = use_case.create(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
            ],
        )
        req = A2AConversationManager.create_request(
            sender=AgentEngineType.CLAUDE_CODE,
            receiver=AgentEngineType.GEMINI_CLI,
            conversation_id=conv.id,
            task_id="t1",
            action=A2AAction.SOLVE,
            payload="do it",
        )
        conv.add_message(req)

        resp = A2AConversationManager.create_response(
            sender=AgentEngineType.GEMINI_CLI,
            request=req,
            payload="done",
        )
        await broker.send(resp)

        # Collect twice — second should add 0
        count1 = await use_case.collect_replies(conv, timeout=1.0)
        count2 = await use_case.collect_replies(conv, timeout=0.1)
        assert count1 == 1
        assert count2 == 0

    def test_summarize(self, use_case: ManageA2AConversationUseCase) -> None:
        conv = use_case.create(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
            ],
        )
        summary = use_case.summarize(conv)
        assert summary.task_id == "t1"
        assert summary.status == A2AConversationStatus.OPEN
        assert summary.message_count == 0
        assert summary.pending_count == 2

    def test_summarize_after_messages(self, use_case: ManageA2AConversationUseCase) -> None:
        conv = use_case.create(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
            ],
        )
        req = A2AConversationManager.create_request(
            sender=AgentEngineType.CLAUDE_CODE,
            receiver=AgentEngineType.GEMINI_CLI,
            conversation_id=conv.id,
            task_id="t1",
            action=A2AAction.REVIEW,
            payload="review this",
        )
        conv.add_message(req)
        resp = A2AConversationManager.create_response(
            sender=AgentEngineType.GEMINI_CLI,
            request=req,
            payload="looks good",
        )
        conv.add_message(resp)
        conv.resolve()

        summary = use_case.summarize(conv)
        assert summary.status == A2AConversationStatus.RESOLVED
        assert summary.message_count == 2
        assert summary.response_count == 1
        assert summary.pending_count == 0

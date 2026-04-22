"""Tests for A2A Protocol domain model (Sprint 18.2 — Phase 14.1).

Covers value objects, entities, and pure domain services.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from domain.entities.a2a import A2AConversation, A2AMessage, AgentDescriptor
from domain.entities.cognitive import AgentAffinityScore
from domain.services.a2a_conversation_manager import A2AConversationManager
from domain.services.a2a_router import A2ARouter
from domain.value_objects.a2a import (
    A2AAction,
    A2AConversationStatus,
    A2AMessageType,
)
from domain.value_objects.agent_engine import AgentEngineType

# ===========================================================================
# Value Objects
# ===========================================================================


class TestA2AValueObjects:
    """A2A enums are str-typed and have expected members."""

    def test_message_types(self) -> None:
        assert A2AMessageType.REQUEST.value == "request"
        assert A2AMessageType.RESPONSE.value == "response"
        assert A2AMessageType.BROADCAST.value == "broadcast"
        assert len(A2AMessageType) == 5

    def test_actions(self) -> None:
        assert A2AAction.SOLVE.value == "solve"
        assert A2AAction.CRITIQUE.value == "critique"
        assert len(A2AAction) == 6

    def test_conversation_status(self) -> None:
        assert A2AConversationStatus.OPEN.value == "open"
        assert A2AConversationStatus.RESOLVED.value == "resolved"
        assert len(A2AConversationStatus) == 4


# ===========================================================================
# A2AMessage Entity
# ===========================================================================


def _msg(
    sender: AgentEngineType = AgentEngineType.CLAUDE_CODE,
    receiver: AgentEngineType | None = AgentEngineType.GEMINI_CLI,
    msg_type: A2AMessageType = A2AMessageType.REQUEST,
    action: A2AAction = A2AAction.SOLVE,
    payload: str = "do something",
    conversation_id: str = "conv-1",
    task_id: str = "task-1",
    reply_to: str | None = None,
) -> A2AMessage:
    return A2AMessage(
        sender=sender,
        receiver=receiver,
        message_type=msg_type,
        action=action,
        payload=payload,
        conversation_id=conversation_id,
        task_id=task_id,
        reply_to=reply_to,
    )


class TestA2AMessage:
    def test_create_basic(self) -> None:
        m = _msg()
        assert m.sender == AgentEngineType.CLAUDE_CODE
        assert m.receiver == AgentEngineType.GEMINI_CLI
        assert m.message_type == A2AMessageType.REQUEST
        assert m.action == A2AAction.SOLVE
        assert len(m.id) > 0

    def test_broadcast_detection(self) -> None:
        m = _msg(receiver=None)
        assert m.is_broadcast is True

    def test_not_broadcast(self) -> None:
        m = _msg()
        assert m.is_broadcast is False

    def test_reply_to_field(self) -> None:
        original = _msg()
        reply = _msg(reply_to=original.id)
        assert reply.reply_to == original.id

    def test_artifacts(self) -> None:
        m = _msg()
        assert m.artifacts == {}
        m2 = A2AMessage(
            sender=AgentEngineType.OLLAMA,
            message_type=A2AMessageType.RESPONSE,
            action=A2AAction.INFORM,
            task_id="t1",
            conversation_id="c1",
            artifacts={"code": "print('hello')"},
        )
        assert m2.artifacts["code"] == "print('hello')"

    def test_rejects_empty_task_id(self) -> None:
        with pytest.raises(ValueError):
            A2AMessage(
                sender=AgentEngineType.OLLAMA,
                message_type=A2AMessageType.REQUEST,
                action=A2AAction.SOLVE,
                task_id="",
                conversation_id="c1",
            )

    def test_timestamp_auto_set(self) -> None:
        m = _msg()
        assert isinstance(m.timestamp, datetime)


# ===========================================================================
# A2AConversation Entity
# ===========================================================================


class TestA2AConversation:
    def test_create(self) -> None:
        c = A2AConversation(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
            ],
        )
        assert c.status == A2AConversationStatus.OPEN
        assert c.message_count == 0
        assert c.is_open is True

    def test_add_message(self) -> None:
        c = A2AConversation(
            task_id="t1",
            participants=[AgentEngineType.CLAUDE_CODE],
        )
        m = _msg(conversation_id=c.id)
        c.add_message(m)
        assert c.message_count == 1
        assert c.last_message is m

    def test_resolve(self) -> None:
        c = A2AConversation(
            task_id="t1",
            participants=[AgentEngineType.CLAUDE_CODE],
        )
        c.resolve()
        assert c.status == A2AConversationStatus.RESOLVED
        assert c.resolved_at is not None
        assert c.is_open is False

    def test_mark_error(self) -> None:
        c = A2AConversation(
            task_id="t1",
            participants=[AgentEngineType.CLAUDE_CODE],
        )
        c.mark_error()
        assert c.status == A2AConversationStatus.ERROR

    def test_mark_timeout(self) -> None:
        c = A2AConversation(
            task_id="t1",
            participants=[AgentEngineType.CLAUDE_CODE],
        )
        c.mark_timeout()
        assert c.status == A2AConversationStatus.TIMEOUT

    def test_get_messages_by_sender(self) -> None:
        c = A2AConversation(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
            ],
        )
        m1 = _msg(sender=AgentEngineType.CLAUDE_CODE)
        m2 = _msg(sender=AgentEngineType.GEMINI_CLI)
        c.add_message(m1)
        c.add_message(m2)
        claude_msgs = c.get_messages_by_sender(AgentEngineType.CLAUDE_CODE)
        assert len(claude_msgs) == 1
        assert claude_msgs[0].sender == AgentEngineType.CLAUDE_CODE

    def test_get_responses(self) -> None:
        c = A2AConversation(
            task_id="t1",
            participants=[AgentEngineType.CLAUDE_CODE],
        )
        c.add_message(_msg(msg_type=A2AMessageType.REQUEST))
        c.add_message(
            _msg(
                msg_type=A2AMessageType.RESPONSE,
                sender=AgentEngineType.GEMINI_CLI,
            )
        )
        assert len(c.get_responses()) == 1

    def test_last_message_none_when_empty(self) -> None:
        c = A2AConversation(
            task_id="t1",
            participants=[AgentEngineType.CLAUDE_CODE],
        )
        assert c.last_message is None

    def test_rejects_empty_participants(self) -> None:
        with pytest.raises(ValueError):
            A2AConversation(task_id="t1", participants=[])

    def test_ttl_default(self) -> None:
        c = A2AConversation(
            task_id="t1",
            participants=[AgentEngineType.CLAUDE_CODE],
        )
        assert c.ttl_seconds == 300


# ===========================================================================
# AgentDescriptor Entity
# ===========================================================================


class TestAgentDescriptor:
    def test_create(self) -> None:
        d = AgentDescriptor(
            engine_type=AgentEngineType.CLAUDE_CODE,
            capabilities=["code", "review"],
        )
        assert d.status == "available"
        assert d.has_capability("code") is True
        assert d.has_capability("Code") is True  # case-insensitive

    def test_has_capability_missing(self) -> None:
        d = AgentDescriptor(
            engine_type=AgentEngineType.OLLAMA,
            capabilities=["code"],
        )
        assert d.has_capability("review") is False

    def test_update_heartbeat(self) -> None:
        d = AgentDescriptor(
            engine_type=AgentEngineType.OLLAMA,
            last_seen=datetime(2020, 1, 1),
        )
        d.update_heartbeat()
        assert d.last_seen.year >= 2026


# ===========================================================================
# A2ARouter Service
# ===========================================================================


def _descriptor(engine: AgentEngineType, caps: list[str]) -> AgentDescriptor:
    return AgentDescriptor(engine_type=engine, capabilities=caps)


class TestA2ARouter:
    def test_basic_routing(self) -> None:
        candidates = [
            _descriptor(AgentEngineType.CLAUDE_CODE, ["code", "review"]),
            _descriptor(AgentEngineType.GEMINI_CLI, ["synthesize"]),
        ]
        result = A2ARouter.select_receiver(A2AAction.REVIEW, candidates)
        # Claude has "review" capability
        assert result == AgentEngineType.CLAUDE_CODE

    def test_exclude_sender(self) -> None:
        candidates = [
            _descriptor(AgentEngineType.CLAUDE_CODE, ["code"]),
            _descriptor(AgentEngineType.GEMINI_CLI, ["code"]),
        ]
        result = A2ARouter.select_receiver(
            A2AAction.SOLVE,
            candidates,
            exclude=AgentEngineType.CLAUDE_CODE,
        )
        assert result == AgentEngineType.GEMINI_CLI

    def test_no_candidates(self) -> None:
        result = A2ARouter.select_receiver(A2AAction.SOLVE, [])
        assert result is None

    def test_all_excluded(self) -> None:
        candidates = [
            _descriptor(AgentEngineType.CLAUDE_CODE, ["code"]),
        ]
        result = A2ARouter.select_receiver(
            A2AAction.SOLVE,
            candidates,
            exclude=AgentEngineType.CLAUDE_CODE,
        )
        assert result is None

    def test_fallback_when_no_capability_match(self) -> None:
        candidates = [
            _descriptor(AgentEngineType.OLLAMA, ["summarize"]),
        ]
        # SOLVE wants "code" but none have it → fallback to first
        result = A2ARouter.select_receiver(A2AAction.SOLVE, candidates)
        assert result == AgentEngineType.OLLAMA

    def test_affinity_scoring(self) -> None:
        candidates = [
            _descriptor(AgentEngineType.CLAUDE_CODE, ["code"]),
            _descriptor(AgentEngineType.GEMINI_CLI, ["code"]),
        ]
        affinities = [
            AgentAffinityScore(
                engine=AgentEngineType.CLAUDE_CODE,
                topic="python",
                familiarity=0.3,
                recency=0.5,
                success_rate=0.4,
                cost_efficiency=0.2,
            ),
            AgentAffinityScore(
                engine=AgentEngineType.GEMINI_CLI,
                topic="python",
                familiarity=0.9,
                recency=0.8,
                success_rate=0.9,
                cost_efficiency=0.7,
            ),
        ]
        result = A2ARouter.select_receiver(A2AAction.SOLVE, candidates, affinities=affinities)
        # Gemini has much higher affinity
        assert result == AgentEngineType.GEMINI_CLI

    def test_affinity_with_exclude(self) -> None:
        candidates = [
            _descriptor(AgentEngineType.CLAUDE_CODE, ["code"]),
            _descriptor(AgentEngineType.GEMINI_CLI, ["code"]),
            _descriptor(AgentEngineType.OLLAMA, ["code"]),
        ]
        affinities = [
            AgentAffinityScore(
                engine=AgentEngineType.GEMINI_CLI,
                topic="x",
                familiarity=0.9,
                success_rate=0.9,
            ),
        ]
        result = A2ARouter.select_receiver(
            A2AAction.SOLVE,
            candidates,
            affinities=affinities,
            exclude=AgentEngineType.GEMINI_CLI,
        )
        # Gemini excluded despite high affinity → Claude or Ollama
        assert result in (
            AgentEngineType.CLAUDE_CODE,
            AgentEngineType.OLLAMA,
        )


# ===========================================================================
# A2AConversationManager Service
# ===========================================================================


class TestA2AConversationManager:
    def test_create_conversation(self) -> None:
        c = A2AConversationManager.create_conversation(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
            ],
        )
        assert c.task_id == "t1"
        assert c.is_open is True
        assert len(c.participants) == 2

    def test_create_request(self) -> None:
        m = A2AConversationManager.create_request(
            sender=AgentEngineType.CLAUDE_CODE,
            receiver=AgentEngineType.GEMINI_CLI,
            conversation_id="c1",
            task_id="t1",
            action=A2AAction.SOLVE,
            payload="implement auth",
        )
        assert m.message_type == A2AMessageType.REQUEST
        assert m.payload == "implement auth"

    def test_create_response(self) -> None:
        req = _msg()
        resp = A2AConversationManager.create_response(
            sender=AgentEngineType.GEMINI_CLI,
            request=req,
            payload="done",
        )
        assert resp.message_type == A2AMessageType.RESPONSE
        assert resp.receiver == req.sender
        assert resp.reply_to == req.id
        assert resp.conversation_id == req.conversation_id

    def test_is_expired(self) -> None:
        c = A2AConversationManager.create_conversation(
            task_id="t1",
            participants=[AgentEngineType.OLLAMA],
            ttl_seconds=60,
        )
        now = c.created_at + timedelta(seconds=61)
        assert A2AConversationManager.is_expired(c, now=now) is True

    def test_not_expired(self) -> None:
        c = A2AConversationManager.create_conversation(
            task_id="t1",
            participants=[AgentEngineType.OLLAMA],
            ttl_seconds=300,
        )
        now = c.created_at + timedelta(seconds=10)
        assert A2AConversationManager.is_expired(c, now=now) is False

    def test_has_all_responses(self) -> None:
        c = A2AConversationManager.create_conversation(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
                AgentEngineType.OLLAMA,
            ],
        )
        # Claude sends request
        req = _msg(
            sender=AgentEngineType.CLAUDE_CODE,
            msg_type=A2AMessageType.REQUEST,
            conversation_id=c.id,
        )
        c.add_message(req)

        # Gemini responds
        c.add_message(
            _msg(
                sender=AgentEngineType.GEMINI_CLI,
                msg_type=A2AMessageType.RESPONSE,
                conversation_id=c.id,
            )
        )
        assert A2AConversationManager.has_all_responses(c) is False

        # Ollama responds → all done
        c.add_message(
            _msg(
                sender=AgentEngineType.OLLAMA,
                msg_type=A2AMessageType.RESPONSE,
                conversation_id=c.id,
            )
        )
        assert A2AConversationManager.has_all_responses(c) is True

    def test_pending_participants(self) -> None:
        c = A2AConversationManager.create_conversation(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
                AgentEngineType.OLLAMA,
            ],
        )
        req = _msg(
            sender=AgentEngineType.CLAUDE_CODE,
            msg_type=A2AMessageType.REQUEST,
            conversation_id=c.id,
        )
        c.add_message(req)
        c.add_message(
            _msg(
                sender=AgentEngineType.GEMINI_CLI,
                msg_type=A2AMessageType.RESPONSE,
                conversation_id=c.id,
            )
        )

        pending = A2AConversationManager.pending_participants(c)
        assert pending == [AgentEngineType.OLLAMA]

    def test_no_requests_all_pending(self) -> None:
        c = A2AConversationManager.create_conversation(
            task_id="t1",
            participants=[
                AgentEngineType.CLAUDE_CODE,
                AgentEngineType.GEMINI_CLI,
            ],
        )
        pending = A2AConversationManager.pending_participants(c)
        assert len(pending) == 2

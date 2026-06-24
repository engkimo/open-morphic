"""Domain tests for Morphic Chat CLI Phase 1 models and ports."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from domain.entities.approval import (
    ApprovalDecision,
    ApprovalDecisionStatus,
    ApprovalRequest,
    ApprovalStatus,
)
from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.entities.chat_session import ChatSession, ChatSessionStatus, PermissionMode
from domain.entities.council_runtime import CouncilDecision, CouncilRole, CouncilTurn
from domain.entities.workspace_context import (
    ContextIndex,
    ContextSourceType,
    WorkspaceContextSource,
)
from domain.ports.chat_session_store import ChatSessionStorePort
from domain.ports.context_discovery import ContextDiscoveryPort
from domain.ports.council_runtime import CouncilRuntimePort
from domain.ports.engine_registry import EngineProfile, EngineRegistryPort, EngineRuntimeKind
from domain.ports.tool_executor import ToolExecutionRequest, ToolExecutionResult, ToolExecutorPort
from domain.value_objects import RiskLevel


def test_chat_event_requires_ordered_append_only_fields() -> None:
    event = ChatEvent(
        type=ChatEventType.USER_MESSAGE,
        session_id="chat-1",
        sequence=0,
        created_at=datetime(2026, 6, 24, tzinfo=UTC),
        payload={"text": "fix tests"},
    )

    assert event.type is ChatEventType.USER_MESSAGE
    assert event.session_id == "chat-1"
    assert event.sequence == 0
    assert event.payload == {"text": "fix tests"}


def test_chat_event_rejects_raw_event_type_and_negative_sequence() -> None:
    with pytest.raises(ValidationError):
        ChatEvent(
            type="user_message",
            session_id="chat-1",
            sequence=0,
            payload={"text": "fix tests"},
        )

    with pytest.raises(ValidationError):
        ChatEvent(
            type=ChatEventType.USER_MESSAGE,
            session_id="chat-1",
            sequence=-1,
            payload={"text": "fix tests"},
        )


def test_chat_session_records_events_without_mutating_previous_state() -> None:
    session = ChatSession.start(
        session_id="chat-1",
        goal="Implement Morphic Chat CLI",
        permission_mode=PermissionMode.CONFIRM_DESTRUCTIVE,
    )

    updated, event = session.record_event(
        ChatEventType.USER_MESSAGE,
        {"text": "start with domain"},
        created_at=datetime(2026, 6, 24, tzinfo=UTC),
    )

    assert session.next_sequence == 0
    assert updated.next_sequence == 1
    assert event.sequence == 0
    assert event.session_id == "chat-1"
    assert updated.status is ChatSessionStatus.ACTIVE


def test_chat_session_close_marks_terminal_state() -> None:
    session = ChatSession.start(
        session_id="chat-1",
        goal=None,
        permission_mode=PermissionMode.READ_ONLY,
    )

    closed = session.close()

    assert closed.status is ChatSessionStatus.ENDED
    assert session.status is ChatSessionStatus.ACTIVE


def test_chat_session_rejects_empty_goal() -> None:
    with pytest.raises(ValidationError):
        ChatSession.start(
            session_id="chat-1",
            goal="",
            permission_mode=PermissionMode.READ_ONLY,
        )


def test_context_index_tracks_sources_with_precedence_and_provenance() -> None:
    source = WorkspaceContextSource(
        source_path="AGENTS.md",
        source_type=ContextSourceType.AGENTS_MD,
        scope="root",
        precedence=100,
        content_hash="sha256:abc123",
        sections=["Architecture", "Tests"],
    )
    index = ContextIndex(workspace_root="/repo", sources=[source])

    assert index.sources_for_type(ContextSourceType.AGENTS_MD) == [source]
    assert index.highest_precedence_source == source


def test_context_source_rejects_empty_path_and_negative_precedence() -> None:
    with pytest.raises(ValidationError):
        WorkspaceContextSource(
            source_path="",
            source_type=ContextSourceType.AGENTS_MD,
            scope="root",
            precedence=100,
            content_hash="sha256:abc123",
        )

    with pytest.raises(ValidationError):
        WorkspaceContextSource(
            source_path="AGENTS.md",
            source_type=ContextSourceType.AGENTS_MD,
            scope="root",
            precedence=-1,
            content_hash="sha256:abc123",
        )


def test_approval_request_and_decision_share_risk_and_status() -> None:
    request = ApprovalRequest(
        id="approval-1",
        session_id="chat-1",
        action_summary="Edit domain entities",
        risk_level=RiskLevel.MEDIUM,
        reason="workspace mutation",
        options=["approve", "deny"],
    )
    decision = ApprovalDecision(
        request_id=request.id,
        status=ApprovalDecisionStatus.APPROVED,
        decided_by="user",
        rationale="safe scoped edit",
    )

    assert request.status is ApprovalStatus.PENDING
    assert request.requires_user_decision
    assert decision.status is ApprovalDecisionStatus.APPROVED


def test_council_turns_separate_roles_from_engines() -> None:
    planner_turn = CouncilTurn(
        role=CouncilRole.PLANNER,
        engine_id="ollama",
        content="Use a minimal domain model first.",
        evidence=["Phase 1 tasks only require entities and ports."],
    )
    decision = CouncilDecision(
        leader_engine_id="direct_llm",
        selected_role=CouncilRole.PLANNER,
        selected_content=planner_turn.content,
        rationale="Lowest blast radius and directly satisfies tasks.",
        evidence=planner_turn.evidence,
    )

    assert planner_turn.role is CouncilRole.PLANNER
    assert planner_turn.engine_id == "ollama"
    assert decision.selected_role is CouncilRole.PLANNER


def test_phase_1_ports_are_abstract_contracts() -> None:
    assert inspect.isabstract(ChatSessionStorePort)
    assert inspect.isabstract(ContextDiscoveryPort)
    assert inspect.isabstract(CouncilRuntimePort)
    assert inspect.isabstract(ToolExecutorPort)
    assert inspect.isabstract(EngineRegistryPort)


def test_tool_executor_contract_uses_risk_classification() -> None:
    request = ToolExecutionRequest(
        session_id="chat-1",
        tool_name="shell",
        arguments={"cmd": "uv run pytest tests/unit/domain -v"},
        risk_level=RiskLevel.LOW,
        requires_approval=False,
    )
    result = ToolExecutionResult(
        request_id=request.id,
        success=True,
        stdout_summary="1 passed",
        stderr_summary="",
        artifacts=[],
    )

    assert request.risk_level is RiskLevel.LOW
    assert result.request_id == request.id
    assert result.success


def test_engine_registry_profile_models_runtime_capabilities() -> None:
    profile = EngineProfile(
        id="ollama",
        display_name="Ollama",
        kind=EngineRuntimeKind.LOCAL_MODEL,
        capabilities=["planning", "drafting"],
        available=True,
        supports_streaming=True,
        supports_editing=False,
        supports_sandbox=False,
    )

    assert profile.id == "ollama"
    assert profile.kind is EngineRuntimeKind.LOCAL_MODEL
    assert "planning" in profile.capabilities

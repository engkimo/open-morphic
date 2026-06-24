"""Infrastructure adapter tests for Morphic Chat CLI Phase 3."""

from __future__ import annotations

import json

import pytest

from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.entities.chat_session import ChatSession, PermissionMode
from domain.entities.council_runtime import CouncilRole
from domain.entities.workspace_context import ContextSourceType
from infrastructure.chat.jsonl_session_store import JsonlChatSessionStore
from infrastructure.context.workspace_context_discovery import WorkspaceContextDiscovery
from infrastructure.council.local_chat_council_runtime import LocalChatCouncilRuntime
from infrastructure.engines.static_engine_registry import StaticEngineRegistry


@pytest.mark.asyncio
async def test_jsonl_session_store_appends_loads_and_finds_latest(tmp_path) -> None:
    store = JsonlChatSessionStore(workspace_root=tmp_path)
    first = ChatEvent(
        type=ChatEventType.SESSION_STARTED,
        session_id="chat-1",
        sequence=0,
        payload={"goal": "one"},
    )
    second = ChatEvent(
        type=ChatEventType.USER_MESSAGE,
        session_id="chat-1",
        sequence=1,
        payload={"text": "hello"},
    )

    await store.append_event(first)
    await store.append_event(second)

    loaded = await store.load_events("chat-1")
    assert loaded == [first, second]
    assert await store.latest_session_id() == "chat-1"
    assert (tmp_path / ".morphic" / "sessions" / "chat-1.jsonl").exists()


@pytest.mark.asyncio
async def test_jsonl_session_store_is_append_only(tmp_path) -> None:
    store = JsonlChatSessionStore(workspace_root=tmp_path)

    await store.append_event(
        ChatEvent(
            type=ChatEventType.SESSION_STARTED,
            session_id="chat-1",
            sequence=0,
            payload={"goal": "one"},
        )
    )
    before = (tmp_path / ".morphic" / "sessions" / "chat-1.jsonl").read_text()
    await store.append_event(
        ChatEvent(
            type=ChatEventType.SESSION_SUMMARY,
            session_id="chat-1",
            sequence=1,
            payload={"event_count": 1},
        )
    )
    after = (tmp_path / ".morphic" / "sessions" / "chat-1.jsonl").read_text()

    assert after.startswith(before)
    assert len(after.splitlines()) == 2


@pytest.mark.asyncio
async def test_workspace_context_discovery_indexes_known_sources_without_editing(tmp_path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Root Rules\n\n- Keep domain pure\n", encoding="utf-8")
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("# Router\n\nSee docs.\n", encoding="utf-8")
    gemini = tmp_path / "GEMINI.md"
    gemini.write_text("# Gemini\n\nLong context.\n", encoding="utf-8")
    command_dir = tmp_path / ".claude" / "commands"
    command_dir.mkdir(parents=True)
    command_file = command_dir / "test.md"
    command_file.write_text("# Test Command\n\nRun tests.\n", encoding="utf-8")
    before_agents = agents.read_text(encoding="utf-8")

    index = await WorkspaceContextDiscovery().discover(str(tmp_path))

    source_types = {source.source_type for source in index.sources}
    assert ContextSourceType.AGENTS_MD in source_types
    assert ContextSourceType.CLAUDE_MD in source_types
    assert ContextSourceType.GEMINI_MD in source_types
    assert ContextSourceType.CLAUDE_COMMANDS in source_types
    assert agents.read_text(encoding="utf-8") == before_agents

    index_path = tmp_path / ".morphic" / "context" / "index.json"
    assert index_path.exists()
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert payload["workspace_root"] == str(tmp_path)
    assert len(payload["sources"]) == len(index.sources)


@pytest.mark.asyncio
async def test_local_chat_council_runtime_returns_role_turns_and_leader_decision(tmp_path) -> None:
    context = await WorkspaceContextDiscovery().discover(str(tmp_path))
    session = ChatSession.start(
        session_id="chat-1",
        goal="Build chat CLI",
        permission_mode=PermissionMode.READ_ONLY,
    )

    turns, decision = await LocalChatCouncilRuntime().deliberate(
        session=session,
        context=context,
        user_message="plan the next step",
    )

    assert [turn.role for turn in turns] == [
        CouncilRole.PLANNER,
        CouncilRole.CRITIC,
        CouncilRole.LEADER,
    ]
    assert decision.selected_role is CouncilRole.PLANNER
    assert "plan the next step" in decision.selected_content


@pytest.mark.asyncio
async def test_static_engine_registry_lists_initial_chat_engines() -> None:
    registry = StaticEngineRegistry()

    engines = await registry.list_engines()
    engine_ids = {engine.id for engine in engines}

    assert {
        "ollama",
        "direct_llm",
        "codex_cli",
        "claude_code",
        "gemini_cli",
        "openhands",
    } <= engine_ids
    assert (await registry.get_engine("ollama")) is not None
    assert await registry.get_engine("missing") is None

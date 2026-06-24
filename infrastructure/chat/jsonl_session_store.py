"""JSONL chat session store for `.morphic/sessions`."""

from __future__ import annotations

import json
from pathlib import Path

from domain.entities.chat_event import ChatEvent
from domain.ports.chat_session_store import ChatSessionStorePort


class JsonlChatSessionStore(ChatSessionStorePort):
    """Append-only session event store backed by one JSONL file per session."""

    def __init__(self, *, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root)
        self._sessions_dir = self._workspace_root / ".morphic" / "sessions"

    async def append_event(self, event: ChatEvent) -> None:
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        path = self._path_for(event.session_id)
        payload = event.model_dump(mode="json")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    async def load_events(self, session_id: str) -> list[ChatEvent]:
        path = self._path_for(session_id)
        if not path.exists():
            return []
        events: list[ChatEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(ChatEvent.model_validate_json(line))
        return events

    async def latest_session_id(self) -> str | None:
        if not self._sessions_dir.exists():
            return None
        files = sorted(
            self._sessions_dir.glob("*.jsonl"),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
        )
        if not files:
            return None
        return files[-1].stem

    def _path_for(self, session_id: str) -> Path:
        return self._sessions_dir / f"{session_id}.jsonl"

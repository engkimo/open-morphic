"""Read-only workspace context discovery for Morphic Chat CLI."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from domain.entities.workspace_context import (
    ContextIndex,
    ContextSourceType,
    WorkspaceContextSource,
)
from domain.ports.context_discovery import ContextDiscoveryPort


class WorkspaceContextDiscovery(ContextDiscoveryPort):
    """Discover known instruction sources and write `.morphic/context/index.json`."""

    _ROOT_FILES: tuple[tuple[str, ContextSourceType, int], ...] = (
        ("AGENTS.md", ContextSourceType.AGENTS_MD, 1000),
        ("CLAUDE.md", ContextSourceType.CLAUDE_MD, 900),
        ("GEMINI.md", ContextSourceType.GEMINI_MD, 800),
        (".github/copilot-instructions.md", ContextSourceType.COPILOT_INSTRUCTIONS, 700),
    )
    _SOURCE_DIRS: tuple[tuple[str, ContextSourceType, int], ...] = (
        (".morphic/context", ContextSourceType.MORPHIC_CONTEXT, 950),
        (".morphic/memory", ContextSourceType.MORPHIC_MEMORY, 850),
        (".claude/agents", ContextSourceType.CLAUDE_AGENTS, 760),
        (".claude/skills", ContextSourceType.CLAUDE_SKILLS, 750),
        (".claude/commands", ContextSourceType.CLAUDE_COMMANDS, 740),
        (".claude/rules", ContextSourceType.CLAUDE_RULES, 730),
        (".cursor/rules", ContextSourceType.CURSOR_RULES, 720),
    )

    async def discover(self, workspace_root: str) -> ContextIndex:
        root = Path(workspace_root)
        sources: list[WorkspaceContextSource] = []

        for relative_path, source_type, precedence in self._ROOT_FILES:
            path = root / relative_path
            if path.is_file():
                sources.append(self._source_for(root, path, source_type, precedence))

        for relative_dir, source_type, precedence in self._SOURCE_DIRS:
            directory = root / relative_dir
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*")):
                if path.is_file() and path.name != "index.json":
                    sources.append(self._source_for(root, path, source_type, precedence))

        index = ContextIndex(workspace_root=str(root), sources=sources)
        self._write_index(root, index)
        return index

    def _source_for(
        self,
        root: Path,
        path: Path,
        source_type: ContextSourceType,
        precedence: int,
    ) -> WorkspaceContextSource:
        content = path.read_text(encoding="utf-8")
        return WorkspaceContextSource(
            source_path=str(path.relative_to(root)),
            source_type=source_type,
            scope=self._scope_for(path.relative_to(root)),
            precedence=precedence,
            content_hash=f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}",
            sections=self._sections_for(content),
        )

    def _write_index(self, root: Path, index: ContextIndex) -> None:
        context_dir = root / ".morphic" / "context"
        context_dir.mkdir(parents=True, exist_ok=True)
        payload = index.model_dump(mode="json")
        (context_dir / "index.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _sections_for(self, content: str) -> list[str]:
        sections: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                if title:
                    sections.append(title)
        return sections

    def _scope_for(self, relative_path: Path) -> str:
        if len(relative_path.parts) == 1:
            return "root"
        return str(relative_path.parent)

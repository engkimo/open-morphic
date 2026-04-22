"""KnowledgeFileLoader — reads engine-specific context files from the project root.

Maps each AgentEngineType to its conventional knowledge file:
- Claude Code → CLAUDE.md
- Codex CLI   → AGENTS.md
- Gemini CLI  → llms-full.txt
- ADK         → llms-full.txt
- Others      → None (no knowledge file)

Used by RouteToEngineUseCase to prepend project context before engine execution.
"""

from __future__ import annotations

import logging
from pathlib import Path

from domain.value_objects.agent_engine import AgentEngineType

logger = logging.getLogger(__name__)

_ENGINE_KNOWLEDGE_FILES: dict[AgentEngineType, str | None] = {
    AgentEngineType.CLAUDE_CODE: "CLAUDE.md",
    AgentEngineType.CODEX_CLI: "AGENTS.md",
    AgentEngineType.GEMINI_CLI: "llms-full.txt",
    AgentEngineType.ADK: "llms-full.txt",
    AgentEngineType.OLLAMA: None,
    AgentEngineType.OPENHANDS: None,
}


class KnowledgeFileLoader:
    """Loads engine-specific knowledge files from a project root directory."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._root = project_root or Path.cwd()

    @property
    def project_root(self) -> Path:
        return self._root

    def load_for_engine(self, engine_type: AgentEngineType) -> str | None:
        """Read the knowledge file for *engine_type*, or return None if absent."""
        filename = _ENGINE_KNOWLEDGE_FILES.get(engine_type)
        if filename is None:
            return None

        path = self._root / filename
        if not path.is_file():
            logger.debug("Knowledge file %s not found for %s", path, engine_type.value)
            return None

        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Failed to read knowledge file %s", path, exc_info=True)
            return None

    def format_context(
        self,
        engine_type: AgentEngineType,
        extra_context: str | None = None,
    ) -> str | None:
        """Build a combined context string from knowledge file + optional extra context.

        Returns None when neither source has content.
        """
        knowledge = self.load_for_engine(engine_type)
        parts: list[str] = []

        if knowledge:
            parts.append(f"[Project Knowledge — {engine_type.value}]\n{knowledge}")

        if extra_context:
            parts.append(extra_context)

        return "\n\n".join(parts) if parts else None

"""Workspace context index entities for Morphic Chat CLI."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ContextSourceType(str, Enum):
    """Known workspace instruction and memory source categories."""

    AGENTS_MD = "agents_md"
    CLAUDE_MD = "claude_md"
    CLAUDE_AGENTS = "claude_agents"
    CLAUDE_SKILLS = "claude_skills"
    CLAUDE_COMMANDS = "claude_commands"
    CLAUDE_RULES = "claude_rules"
    GEMINI_MD = "gemini_md"
    CURSOR_RULES = "cursor_rules"
    COPILOT_INSTRUCTIONS = "copilot_instructions"
    MORPHIC_CONTEXT = "morphic_context"
    MORPHIC_MEMORY = "morphic_memory"
    DOCS_ROUTER = "docs_router"
    OTHER = "other"


class WorkspaceContextSource(BaseModel):
    """One discovered context source with provenance and precedence."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    source_path: str = Field(min_length=1)
    source_type: ContextSourceType
    scope: str = Field(min_length=1)
    precedence: int = Field(ge=0)
    content_hash: str = Field(min_length=1)
    imported_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    sections: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ContextIndex(BaseModel):
    """Normalized read-only view of workspace instruction sources."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    workspace_root: str = Field(min_length=1)
    sources: list[WorkspaceContextSource] = Field(default_factory=list)
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    def sources_for_type(
        self, source_type: ContextSourceType
    ) -> list[WorkspaceContextSource]:
        return [source for source in self.sources if source.source_type is source_type]

    @property
    def highest_precedence_source(self) -> WorkspaceContextSource | None:
        if not self.sources:
            return None
        return max(self.sources, key=lambda source: source.precedence)

"""Tests for KnowledgeFileLoader — engine-specific context file loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.agent_cli.knowledge_loader import KnowledgeFileLoader


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project root with sample knowledge files."""
    (tmp_path / "CLAUDE.md").write_text("# Claude Context\nProject rules here.", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Codex Agents\nCodex rules.", encoding="utf-8")
    (tmp_path / "llms-full.txt").write_text("ADK/Gemini knowledge base content.", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def loader(tmp_project: Path) -> KnowledgeFileLoader:
    return KnowledgeFileLoader(project_root=tmp_project)


# ── Construction ──


class TestConstruction:
    def test_default_root_is_cwd(self):
        loader = KnowledgeFileLoader()
        assert loader.project_root == Path.cwd()

    def test_custom_root(self, tmp_path: Path):
        loader = KnowledgeFileLoader(project_root=tmp_path)
        assert loader.project_root == tmp_path


# ── load_for_engine ──


class TestLoadForEngine:
    def test_claude_code_loads_claude_md(self, loader: KnowledgeFileLoader):
        content = loader.load_for_engine(AgentEngineType.CLAUDE_CODE)
        assert content is not None
        assert "Claude Context" in content

    def test_codex_cli_loads_agents_md(self, loader: KnowledgeFileLoader):
        content = loader.load_for_engine(AgentEngineType.CODEX_CLI)
        assert content is not None
        assert "Codex Agents" in content

    def test_gemini_cli_loads_llms_full(self, loader: KnowledgeFileLoader):
        content = loader.load_for_engine(AgentEngineType.GEMINI_CLI)
        assert content is not None
        assert "ADK/Gemini knowledge" in content

    def test_adk_loads_llms_full(self, loader: KnowledgeFileLoader):
        content = loader.load_for_engine(AgentEngineType.ADK)
        assert content is not None
        assert "ADK/Gemini knowledge" in content

    def test_ollama_returns_none(self, loader: KnowledgeFileLoader):
        assert loader.load_for_engine(AgentEngineType.OLLAMA) is None

    def test_openhands_returns_none(self, loader: KnowledgeFileLoader):
        assert loader.load_for_engine(AgentEngineType.OPENHANDS) is None

    def test_missing_file_returns_none(self, tmp_path: Path):
        """When the knowledge file doesn't exist, returns None."""
        loader = KnowledgeFileLoader(project_root=tmp_path)
        assert loader.load_for_engine(AgentEngineType.CLAUDE_CODE) is None


# ── format_context ──


class TestFormatContext:
    def test_knowledge_only(self, loader: KnowledgeFileLoader):
        result = loader.format_context(AgentEngineType.CLAUDE_CODE)
        assert result is not None
        assert "Project Knowledge" in result
        assert "claude_code" in result
        assert "Claude Context" in result

    def test_extra_context_only(self, tmp_path: Path):
        """Engine with no knowledge file but extra context provided."""
        loader = KnowledgeFileLoader(project_root=tmp_path)
        result = loader.format_context(AgentEngineType.OLLAMA, extra_context="Use Python 3.12")
        assert result == "Use Python 3.12"

    def test_both_combined(self, loader: KnowledgeFileLoader):
        result = loader.format_context(
            AgentEngineType.CLAUDE_CODE, extra_context="Focus on security"
        )
        assert result is not None
        assert "Project Knowledge" in result
        assert "Focus on security" in result

    def test_neither_returns_none(self, tmp_path: Path):
        loader = KnowledgeFileLoader(project_root=tmp_path)
        result = loader.format_context(AgentEngineType.OLLAMA)
        assert result is None

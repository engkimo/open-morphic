"""AgentEngineType — execution engine classification for Agent CLI Orchestration."""

from enum import Enum


class AgentEngineType(str, Enum):
    OPENHANDS = "openhands"
    CLAUDE_CODE = "claude_code"
    GEMINI_CLI = "gemini_cli"
    CODEX_CLI = "codex_cli"
    ADK = "adk"
    OLLAMA = "ollama"

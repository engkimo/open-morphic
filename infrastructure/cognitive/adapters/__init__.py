"""Context adapters — bidirectional UCL ↔ engine context translation.

Each adapter converts SharedTaskState + memory into engine-specific format (inject)
and extracts insights from engine output (extract).
"""

from infrastructure.cognitive.adapters.adk import ADKContextAdapter
from infrastructure.cognitive.adapters.claude_code import ClaudeCodeContextAdapter
from infrastructure.cognitive.adapters.codex import CodexContextAdapter
from infrastructure.cognitive.adapters.gemini import GeminiContextAdapter
from infrastructure.cognitive.adapters.ollama import OllamaContextAdapter
from infrastructure.cognitive.adapters.openhands import OpenHandsContextAdapter

__all__ = [
    "ADKContextAdapter",
    "ClaudeCodeContextAdapter",
    "CodexContextAdapter",
    "GeminiContextAdapter",
    "OllamaContextAdapter",
    "OpenHandsContextAdapter",
]

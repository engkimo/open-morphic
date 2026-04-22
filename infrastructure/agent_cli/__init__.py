"""Agent CLI Orchestration — execution engine drivers.

Six concrete drivers implementing AgentEnginePort:
- OllamaEngineDriver: local LLM via LiteLLMGateway (cost $0)
- ClaudeCodeDriver: Claude Code CLI headless mode
- CodexCLIDriver: OpenAI Codex CLI exec mode
- GeminiCLIDriver: Gemini CLI with 2M token context
- OpenHandsDriver: OpenHands REST API (Docker sandbox)
- ADKDriver: Google ADK (Agent Development Kit) via Python SDK
"""

from infrastructure.agent_cli.adk_driver import ADKDriver
from infrastructure.agent_cli.claude_code_driver import ClaudeCodeDriver
from infrastructure.agent_cli.codex_cli_driver import CodexCLIDriver
from infrastructure.agent_cli.gemini_cli_driver import GeminiCLIDriver
from infrastructure.agent_cli.ollama_driver import OllamaEngineDriver
from infrastructure.agent_cli.openhands_driver import OpenHandsDriver

__all__ = [
    "ADKDriver",
    "ClaudeCodeDriver",
    "CodexCLIDriver",
    "GeminiCLIDriver",
    "OllamaEngineDriver",
    "OpenHandsDriver",
]

"""Static engine registry for Morphic Chat CLI MVP."""

from __future__ import annotations

from domain.ports.engine_registry import (
    EngineProfile,
    EngineRegistryPort,
    EngineRuntimeKind,
)


class StaticEngineRegistry(EngineRegistryPort):
    """Lists known chat engine backends without invoking external CLIs."""

    def __init__(self, profiles: list[EngineProfile] | None = None) -> None:
        self._profiles = profiles or self._default_profiles()

    async def list_engines(self) -> list[EngineProfile]:
        return list(self._profiles)

    async def get_engine(self, engine_id: str) -> EngineProfile | None:
        return next((profile for profile in self._profiles if profile.id == engine_id), None)

    def _default_profiles(self) -> list[EngineProfile]:
        return [
            EngineProfile(
                id="ollama",
                display_name="Ollama",
                kind=EngineRuntimeKind.LOCAL_MODEL,
                capabilities=["planning", "drafting"],
                available=False,
                cost_profile="local",
                latency_profile="low",
                supports_streaming=True,
            ),
            EngineProfile(
                id="direct_llm",
                display_name="Direct LLM Gateway",
                kind=EngineRuntimeKind.DIRECT_API,
                capabilities=["planning", "summarization", "tool_calling"],
                available=False,
                cost_profile="provider",
                supports_json_output=True,
            ),
            EngineProfile(
                id="codex_cli",
                display_name="Codex CLI",
                kind=EngineRuntimeKind.EXTERNAL_CLI,
                capabilities=["code_generation", "workspace_editing"],
                available=False,
                supports_editing=True,
            ),
            EngineProfile(
                id="claude_code",
                display_name="Claude Code",
                kind=EngineRuntimeKind.EXTERNAL_CLI,
                capabilities=["architecture_review", "workspace_editing"],
                available=False,
                supports_editing=True,
                supports_streaming=True,
            ),
            EngineProfile(
                id="gemini_cli",
                display_name="Gemini CLI",
                kind=EngineRuntimeKind.EXTERNAL_CLI,
                capabilities=["long_context", "planning"],
                available=False,
                supports_streaming=True,
            ),
            EngineProfile(
                id="openhands",
                display_name="OpenHands",
                kind=EngineRuntimeKind.SANDBOX_RUNTIME,
                capabilities=["sandbox_execution", "workspace_editing"],
                available=False,
                supports_editing=True,
                supports_sandbox=True,
            ),
        ]

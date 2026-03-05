"""ADKDriver — wraps Google ADK (Agent Development Kit) as an AgentEnginePort.

Uses the Python SDK (google-adk) with try-import guard — same pattern as
neo4j/pgvector elsewhere in the codebase.  Sprint 4.5 wraps a single
LlmAgent.run() call; SequentialAgent/ParallelAgent workflows are Phase 5+ scope.
"""

from __future__ import annotations

import time

from domain.ports.agent_engine import (
    AgentEngineCapabilities,
    AgentEnginePort,
    AgentEngineResult,
)
from domain.value_objects.agent_engine import AgentEngineType

# Optional dependency guard — google-adk is an optional extra
try:
    from google.adk.agents import LlmAgent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part

    _ADK_AVAILABLE = True
except ImportError:
    LlmAgent = None  # type: ignore[assignment,misc]
    Runner = None  # type: ignore[assignment,misc]
    InMemorySessionService = None  # type: ignore[assignment,misc]
    Content = None  # type: ignore[assignment,misc]
    Part = None  # type: ignore[assignment,misc]
    _ADK_AVAILABLE = False

_DEFAULT_MODEL = "gemini-2.5-flash"


class ADKDriver(AgentEnginePort):
    """Agent engine backed by Google ADK (Agent Development Kit).

    Wraps a single LlmAgent → Runner → run_async cycle.
    Requires ``google-adk`` package (install via ``pip install morphic-agent[adk]``).
    When the package is missing or the driver is disabled, ``run_task`` returns
    an error result without raising.
    """

    engine_type: AgentEngineType = AgentEngineType.ADK

    def __init__(self, enabled: bool = True, model: str = _DEFAULT_MODEL) -> None:
        self._enabled = enabled
        self._model = model

    async def run_task(
        self,
        task: str,
        model: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> AgentEngineResult:
        if not self._enabled:
            return AgentEngineResult(
                engine=AgentEngineType.ADK,
                success=False,
                output="",
                error="ADK driver is disabled",
            )

        if not _ADK_AVAILABLE:
            return AgentEngineResult(
                engine=AgentEngineType.ADK,
                success=False,
                output="",
                error="google-adk package is not installed",
            )

        resolved_model = model or self._model
        start = time.monotonic()
        try:
            agent = LlmAgent(
                name="morphic_adk_agent",
                model=resolved_model,
                instruction="You are a helpful AI assistant.",
            )
            session_service = InMemorySessionService()
            runner = Runner(agent=agent, app_name="morphic-agent", session_service=session_service)
            session = await session_service.create_session(
                app_name="morphic-agent", user_id="morphic"
            )

            user_content = Content(role="user", parts=[Part(text=task)])

            final_text = ""
            async for event in runner.run_async(
                user_id="morphic",
                session_id=session.id,
                new_message=user_content,
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    final_text = "".join(
                        p.text for p in event.content.parts if hasattr(p, "text") and p.text
                    )

            duration = time.monotonic() - start
            return AgentEngineResult(
                engine=AgentEngineType.ADK,
                success=True,
                output=final_text,
                cost_usd=0.0,
                duration_seconds=duration,
                model_used=resolved_model,
            )
        except Exception as exc:
            duration = time.monotonic() - start
            return AgentEngineResult(
                engine=AgentEngineType.ADK,
                success=False,
                output="",
                error=str(exc),
                duration_seconds=duration,
                model_used=resolved_model,
            )

    async def is_available(self) -> bool:
        return self._enabled and _ADK_AVAILABLE

    def get_capabilities(self) -> AgentEngineCapabilities:
        return AgentEngineCapabilities(
            engine_type=AgentEngineType.ADK,
            max_context_tokens=2_000_000,
            supports_sandbox=False,
            supports_parallel=True,
            supports_mcp=True,
            supports_streaming=True,
            cost_per_hour_usd=0.0,
        )

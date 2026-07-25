"""AgentEnginePort — abstraction over agent execution engines.

Each engine (OpenHands, Claude Code, Gemini CLI, Codex CLI, ADK, Ollama)
implements this port. The domain service AgentEngineRouter selects which
engine to use based on task characteristics and budget.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime

from domain.entities.agent_engine_event import AgentEngineEvent
from domain.entities.chat_session import PermissionMode
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.fallback_attempt import FallbackAttempt


@dataclass
class AgentEngineResult:
    """Result of an agent engine task execution."""

    engine: AgentEngineType
    success: bool
    output: str
    artifacts: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    model_used: str | None = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    # Fallback transparency (BUG-003)
    fallback_reason: str | None = None
    engines_tried: list[str] = field(default_factory=list)
    fallback_attempts: list[FallbackAttempt] = field(default_factory=list)


@dataclass(frozen=True)
class AgentEngineCapabilities:
    """Static capabilities of an agent execution engine."""

    engine_type: AgentEngineType
    max_context_tokens: int = 0
    supports_sandbox: bool = False
    supports_parallel: bool = False
    supports_mcp: bool = False
    supports_streaming: bool = False
    cost_per_hour_usd: float = 0.0


class AgentEnginePort(ABC):
    """Abstract interface for agent execution engines.

    Infrastructure layer provides concrete implementations
    (OpenHandsDriver, ClaudeCodeDriver, etc.) in Sprint 4.2+.
    """

    @abstractmethod
    async def run_task(
        self,
        task: str,
        model: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> AgentEngineResult: ...

    @abstractmethod
    async def is_available(self) -> bool: ...

    @abstractmethod
    def get_capabilities(self) -> AgentEngineCapabilities: ...


class ScopedAgentEnginePort(AgentEnginePort):
    """Agent engine that preserves workspace and permission boundaries."""

    @abstractmethod
    async def run_task_scoped(
        self,
        task: str,
        *,
        workspace_root: str,
        permission_mode: PermissionMode,
        model: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> AgentEngineResult: ...


class AgentEngineEventSinkPort(ABC):
    """Consumes normalized native-engine events as they occur."""

    @abstractmethod
    async def publish(self, event: AgentEngineEvent) -> None: ...


class StreamingScopedAgentEnginePort(ScopedAgentEnginePort):
    """Scoped engine that can publish events before process completion."""

    @abstractmethod
    async def run_task_scoped_stream(
        self,
        task: str,
        *,
        workspace_root: str,
        permission_mode: PermissionMode,
        event_sink: AgentEngineEventSinkPort,
        model: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> AgentEngineResult: ...


class ResumableStreamingScopedAgentEnginePort(StreamingScopedAgentEnginePort):
    """Streaming scoped engine that can continue an explicit native session."""

    @abstractmethod
    async def resume_task_scoped_stream(
        self,
        task: str,
        *,
        resume_session_id: str,
        workspace_root: str,
        permission_mode: PermissionMode,
        event_sink: AgentEngineEventSinkPort,
        model: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> AgentEngineResult: ...

"""Port and profile model for chat execution engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class EngineRuntimeKind(str, Enum):
    """Runtime category for an engine profile."""

    EXTERNAL_CLI = "external_cli"
    SDK = "sdk"
    DIRECT_API = "direct_api"
    LOCAL_MODEL = "local_model"
    SANDBOX_RUNTIME = "sandbox_runtime"


class EngineProfile(BaseModel):
    """Discoverable capabilities of an engine backend."""

    model_config = ConfigDict(strict=True, validate_assignment=True, frozen=True)

    id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    kind: EngineRuntimeKind
    capabilities: list[str] = Field(default_factory=list)
    available: bool = False
    cost_profile: str | None = None
    latency_profile: str | None = None
    context_window: int = Field(default=0, ge=0)
    supports_streaming: bool = False
    supports_editing: bool = False
    supports_sandbox: bool = False
    supports_json_output: bool = False


class EngineRegistryPort(ABC):
    """Lists and resolves available chat execution engines."""

    @abstractmethod
    async def list_engines(self) -> list[EngineProfile]: ...

    @abstractmethod
    async def get_engine(self, engine_id: str) -> EngineProfile | None: ...

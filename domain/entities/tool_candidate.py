"""ToolCandidate — A tool discovered from a registry or marketplace."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects.tool_safety import SafetyTier


class ToolCandidate(BaseModel):
    """Represents a tool that can be installed from a registry."""

    model_config = ConfigDict(strict=True, validate_assignment=True)

    name: str = Field(min_length=1)
    description: str = ""
    publisher: str = ""
    package_name: str = ""
    transport: str = "stdio"
    install_command: str = ""
    source_url: str = ""
    download_count: int = Field(default=0, ge=0)
    safety_tier: SafetyTier = SafetyTier.EXPERIMENTAL
    safety_score: float = Field(default=0.0, ge=0.0, le=1.0)
    discovered_at: datetime = Field(default_factory=datetime.now)

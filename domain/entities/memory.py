"""Memory entity — semantic memory entry. Pure domain."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects.status import MemoryType


class MemoryEntry(BaseModel):
    """A single memory entry in the L1-L4 hierarchy."""

    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str = Field(min_length=1)
    memory_type: MemoryType
    access_count: int = Field(default=1, ge=1)
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    last_accessed: datetime = Field(default_factory=datetime.now)

    def reinforce(self) -> None:
        """Increase access count and update last_accessed."""
        self.access_count += 1
        self.last_accessed = datetime.now()

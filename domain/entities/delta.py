"""Delta entity — Git-style state change record. Pure domain."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Delta(BaseModel):
    """A single state change record (like a Git commit).

    Records changes to a named topic's state as a dict diff.
    Deltas are applied in seq order to reconstruct state at any point.
    """

    model_config = ConfigDict(strict=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str = Field(min_length=1)
    seq: int = Field(ge=0)
    message: str = Field(min_length=1)
    changes: dict[str, Any] = Field(min_length=1)
    state_hash: str = Field(min_length=1)
    is_base_state: bool = False
    created_at: datetime = Field(default_factory=datetime.now)

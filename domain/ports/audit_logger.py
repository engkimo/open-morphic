"""AuditLogger port — abstraction for action audit logging."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from domain.entities.execution import Action
from domain.value_objects import RiskLevel


class AuditLogger(ABC):
    @abstractmethod
    def log(
        self, action: Action, result: str, risk: RiskLevel, success: bool = True
    ) -> None: ...

    @abstractmethod
    def query(
        self,
        tool: str | None = None,
        risk: RiskLevel | None = None,
        since: datetime | None = None,
    ) -> list[dict]: ...

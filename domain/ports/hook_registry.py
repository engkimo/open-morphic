"""Port for workspace hook discovery and validation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.hook import HookDefinition, HookDiagnostic, HookType


class HookRegistryPort(ABC):
    """Read-only hook registry contract."""

    @abstractmethod
    def validate(self) -> list[HookDiagnostic]: ...

    @abstractmethod
    def hooks_for(self, hook_type: HookType) -> list[HookDefinition]: ...

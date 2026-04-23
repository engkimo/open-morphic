"""StrategyRepository port — persistence for learned strategies.

Domain defines WHAT it needs. Infrastructure provides HOW.

Single-writer assumption: the only caller today is the Level-2 learning
use case, which runs serially. Ordering on load is unspecified; callers
requiring a specific order shall sort after loading. Partial reads are
acceptable when the persistence medium reports recoverable I/O errors;
specific behavior (skip vs raise, log level) is implementation-local.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.strategy import EnginePreference, ModelPreference, RecoveryRule


class StrategyRepository(ABC):
    @abstractmethod
    def load_recovery_rules(self) -> list[RecoveryRule]: ...

    @abstractmethod
    def save_recovery_rules(self, rules: list[RecoveryRule]) -> None: ...

    @abstractmethod
    def append_recovery_rule(self, rule: RecoveryRule) -> None: ...

    @abstractmethod
    def load_model_preferences(self) -> list[ModelPreference]: ...

    @abstractmethod
    def save_model_preferences(self, prefs: list[ModelPreference]) -> None: ...

    @abstractmethod
    def load_engine_preferences(self) -> list[EnginePreference]: ...

    @abstractmethod
    def save_engine_preferences(self, prefs: list[EnginePreference]) -> None: ...

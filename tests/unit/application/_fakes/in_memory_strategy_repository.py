"""In-memory StrategyRepository fake for unit tests.

Holds three lists in instance attributes; implements the 7 abstract methods
with copy-on-read/write semantics so callers cannot mutate persisted state
through the returned references.
"""

from __future__ import annotations

from domain.entities.strategy import EnginePreference, ModelPreference, RecoveryRule
from domain.ports.strategy_repository import StrategyRepository


class InMemoryStrategyRepository(StrategyRepository):
    def __init__(self) -> None:
        self._recovery_rules: list[RecoveryRule] = []
        self._model_prefs: list[ModelPreference] = []
        self._engine_prefs: list[EnginePreference] = []

    def load_recovery_rules(self) -> list[RecoveryRule]:
        return list(self._recovery_rules)

    def save_recovery_rules(self, rules: list[RecoveryRule]) -> None:
        self._recovery_rules = list(rules)

    def append_recovery_rule(self, rule: RecoveryRule) -> None:
        self._recovery_rules.append(rule)

    def load_model_preferences(self) -> list[ModelPreference]:
        return list(self._model_prefs)

    def save_model_preferences(self, prefs: list[ModelPreference]) -> None:
        self._model_prefs = list(prefs)

    def load_engine_preferences(self) -> list[EnginePreference]:
        return list(self._engine_prefs)

    def save_engine_preferences(self, prefs: list[EnginePreference]) -> None:
        self._engine_prefs = list(prefs)

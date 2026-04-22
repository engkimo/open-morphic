"""StrategyStore — JSONL file-based persistence for learned strategies.

Follows the AuditLog pattern: append-only JSONL for recovery rules,
model preferences, and engine preferences.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from domain.entities.strategy import EnginePreference, ModelPreference, RecoveryRule

logger = logging.getLogger(__name__)


class StrategyStore:
    """JSONL-based persistence for learned strategies.

    Files:
    - {base_dir}/recovery_rules.jsonl
    - {base_dir}/model_preferences.jsonl
    - {base_dir}/engine_preferences.jsonl
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _rules_path(self) -> Path:
        return self._base_dir / "recovery_rules.jsonl"

    @property
    def _model_prefs_path(self) -> Path:
        return self._base_dir / "model_preferences.jsonl"

    @property
    def _engine_prefs_path(self) -> Path:
        return self._base_dir / "engine_preferences.jsonl"

    # ── Recovery Rules ──

    def load_recovery_rules(self) -> list[RecoveryRule]:
        """Load all recovery rules from disk."""
        return self._load_jsonl(self._rules_path, RecoveryRule)

    def save_recovery_rules(self, rules: list[RecoveryRule]) -> None:
        """Overwrite recovery rules file with current state."""
        self._write_jsonl(self._rules_path, rules)

    def append_recovery_rule(self, rule: RecoveryRule) -> None:
        """Append a single recovery rule."""
        self._append_jsonl(self._rules_path, rule)

    # ── Model Preferences ──

    def load_model_preferences(self) -> list[ModelPreference]:
        """Load all model preferences from disk."""
        return self._load_jsonl(self._model_prefs_path, ModelPreference)

    def save_model_preferences(self, prefs: list[ModelPreference]) -> None:
        """Overwrite model preferences file with current state."""
        self._write_jsonl(self._model_prefs_path, prefs)

    # ── Engine Preferences ──

    def load_engine_preferences(self) -> list[EnginePreference]:
        """Load all engine preferences from disk."""
        return self._load_jsonl(self._engine_prefs_path, EnginePreference)

    def save_engine_preferences(self, prefs: list[EnginePreference]) -> None:
        """Overwrite engine preferences file with current state."""
        self._write_jsonl(self._engine_prefs_path, prefs)

    # ── Internal helpers ──

    def _load_jsonl(self, path: Path, model_cls: type) -> list:  # type: ignore[type-arg]
        """Load a JSONL file, parsing each line into a Pydantic model.

        Uses non-strict validation so JSON strings are coerced to enums.
        """
        if not path.exists():
            return []

        results = []
        for line in path.read_text(encoding="utf-8").strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                results.append(model_cls.model_validate(data, strict=False))
            except (json.JSONDecodeError, Exception) as e:
                logger.warning("Skipping invalid JSONL line in %s: %s", path, e)
        return results

    def _write_jsonl(self, path: Path, items: list) -> None:  # type: ignore[type-arg]
        """Overwrite a JSONL file with all items."""
        with open(path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False) + "\n")

    def _append_jsonl(self, path: Path, item: object) -> None:
        """Append a single item to a JSONL file."""
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False) + "\n")  # type: ignore[union-attr]

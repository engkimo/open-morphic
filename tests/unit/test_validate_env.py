"""Tests for scripts/validate_env.py — TD-148."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    """Create a temporary root with .env.example."""
    example = tmp_path / ".env.example"
    example.write_text(
        "ANTHROPIC_API_KEY=\n"
        "LOCAL_FIRST=true\n"
        "DEFAULT_MONTHLY_BUDGET_USD=50\n"
        "OLLAMA_BASE_URL=http://127.0.0.1:11434\n",
        encoding="utf-8",
    )
    return tmp_path


def _validate(root: Path) -> list[str]:
    """Import and call validate()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "validate_env",
        Path(__file__).resolve().parents[2] / "scripts" / "validate_env.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.validate(root)


def test_missing_env_file(tmp_root: Path) -> None:
    warnings = _validate(tmp_root)
    assert any(".env file not found" in w for w in warnings)


def test_valid_env(tmp_root: Path) -> None:
    (tmp_root / ".env").write_text(
        "ANTHROPIC_API_KEY=sk-xxx\n"
        "LOCAL_FIRST=true\n"
        "DEFAULT_MONTHLY_BUDGET_USD=50\n"
        "OLLAMA_BASE_URL=http://127.0.0.1:11434\n",
        encoding="utf-8",
    )
    warnings = _validate(tmp_root)
    assert warnings == []


def test_missing_key(tmp_root: Path) -> None:
    (tmp_root / ".env").write_text(
        "ANTHROPIC_API_KEY=sk-xxx\n",
        encoding="utf-8",
    )
    warnings = _validate(tmp_root)
    assert any("Missing key: LOCAL_FIRST" in w for w in warnings)


def test_invalid_boolean(tmp_root: Path) -> None:
    (tmp_root / ".env").write_text(
        "ANTHROPIC_API_KEY=sk-xxx\n"
        "LOCAL_FIRST=maybe\n"
        "DEFAULT_MONTHLY_BUDGET_USD=50\n"
        "OLLAMA_BASE_URL=http://127.0.0.1:11434\n",
        encoding="utf-8",
    )
    warnings = _validate(tmp_root)
    assert any("Invalid boolean" in w for w in warnings)


def test_invalid_number(tmp_root: Path) -> None:
    (tmp_root / ".env").write_text(
        "ANTHROPIC_API_KEY=sk-xxx\n"
        "LOCAL_FIRST=true\n"
        "DEFAULT_MONTHLY_BUDGET_USD=not_a_number\n"
        "OLLAMA_BASE_URL=http://127.0.0.1:11434\n",
        encoding="utf-8",
    )
    warnings = _validate(tmp_root)
    assert any("Invalid number" in w for w in warnings)

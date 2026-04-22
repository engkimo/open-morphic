#!/usr/bin/env python3
"""Validate .env against .env.example — flag missing required keys."""

from __future__ import annotations

import sys
from pathlib import Path


def parse_env_file(path: Path) -> dict[str, str]:
    """Extract KEY=VALUE pairs, ignoring comments and blanks."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def validate(root: Path | None = None) -> list[str]:
    """Return list of warning messages."""
    root = root or Path(__file__).resolve().parents[1]
    example = parse_env_file(root / ".env.example")
    actual = parse_env_file(root / ".env")
    warnings: list[str] = []

    if not (root / ".env").exists():
        warnings.append(".env file not found — copy .env.example to .env")
        return warnings

    for key in example:
        if key not in actual:
            warnings.append(f"Missing key: {key} (defined in .env.example)")

    # Type-check known booleans
    boolean_keys = {
        "LOCAL_FIRST", "AUTO_DOWNGRADE_ON_BUDGET", "CACHE_BREAKPOINTS_ENABLED",
        "LAEE_ENABLED", "LAEE_UNDO_ENABLED", "LAEE_BROWSER_HEADLESS",
        "LAEE_GUI_ENABLED", "LAEE_CRON_ENABLED", "MCP_ENABLED",
        "EVOLUTION_ENABLED", "AUTO_TOOL_INSTALL",
        "CLAUDE_CODE_SDK_ENABLED", "GEMINI_CLI_ENABLED", "CODEX_CLI_ENABLED",
    }
    for key in boolean_keys & actual.keys():
        if actual[key].lower() not in ("true", "false", "1", "0", ""):
            warnings.append(f"Invalid boolean for {key}: {actual[key]!r}")

    # Type-check known numbers
    numeric_keys = {
        "DEFAULT_MONTHLY_BUDGET_USD", "DEFAULT_TASK_BUDGET_USD",
        "MEMORY_TARGET_TOKENS", "MEMORY_RETENTION_THRESHOLD",
        "LAEE_MAX_CONCURRENT_SHELLS",
    }
    for key in numeric_keys & actual.keys():
        if actual[key]:
            try:
                float(actual[key])
            except ValueError:
                warnings.append(f"Invalid number for {key}: {actual[key]!r}")

    # URL format check
    url_keys = {
        "OLLAMA_BASE_URL", "OPENHANDS_BASE_URL", "DATABASE_URL",
        "REDIS_URL", "NEO4J_URI",
    }
    for key in url_keys & actual.keys():
        val = actual[key]
        if val and not (val.startswith("http") or val.startswith("postgresql") or
                        val.startswith("redis") or val.startswith("bolt") or
                        val.startswith("sqlite")):
            warnings.append(f"Suspicious URL for {key}: {val!r}")

    return warnings


def main() -> int:
    warnings = validate()
    if not warnings:
        print("OK: .env is valid")
        return 0
    for w in warnings:
        print(f"  WARN: {w}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

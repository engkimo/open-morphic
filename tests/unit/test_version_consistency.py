"""Verify version strings are consistent across the project."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_VERSION = "0.5.1"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_pyproject_version():
    content = _read("pyproject.toml")
    match = re.search(r'^version\s*=\s*"(.+?)"', content, re.MULTILINE)
    assert match is not None, "version not found in pyproject.toml"
    assert match.group(1) == EXPECTED_VERSION


def test_fastapi_version():
    content = _read("interface/api/main.py")
    match = re.search(r'version="(.+?)"', content)
    assert match is not None, "version not found in main.py"
    assert match.group(1) == EXPECTED_VERSION


def test_extension_version_prefix():
    """Chrome extension uses semver without prerelease suffix."""
    content = _read("ui/extension/manifest.json")
    match = re.search(r'"version":\s*"(.+?)"', content)
    assert match is not None, "version not found in manifest.json"
    assert match.group(1).startswith("0.5.")

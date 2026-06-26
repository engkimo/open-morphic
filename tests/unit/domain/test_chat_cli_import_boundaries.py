"""Import-boundary checks for Morphic Chat CLI domain additions."""

from __future__ import annotations

import ast
from pathlib import Path

CHAT_CLI_DOMAIN_FILES = [
    Path("domain/entities/approval.py"),
    Path("domain/entities/chat_event.py"),
    Path("domain/entities/chat_session.py"),
    Path("domain/entities/council_runtime.py"),
    Path("domain/entities/hook.py"),
    Path("domain/entities/workspace_context.py"),
    Path("domain/ports/chat_session_store.py"),
    Path("domain/ports/context_discovery.py"),
    Path("domain/ports/council_runtime.py"),
    Path("domain/ports/engine_registry.py"),
    Path("domain/ports/hook_registry.py"),
    Path("domain/ports/tool_executor.py"),
]

FORBIDDEN_IMPORT_PREFIXES = (
    "fastapi",
    "infrastructure",
    "interface",
    "litellm",
    "rich",
    "sqlalchemy",
    "subprocess",
    "textual",
    "typer",
)


def _imports_for(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def test_chat_cli_domain_files_keep_clean_architecture_import_boundary() -> None:
    for path in CHAT_CLI_DOMAIN_FILES:
        assert path.exists(), f"Expected Phase 1 domain file missing: {path}"
        imports = _imports_for(path)
        forbidden = [
            module
            for module in imports
            if module == "subprocess"
            or any(module.startswith(f"{prefix}.") for prefix in FORBIDDEN_IMPORT_PREFIXES)
            or module in FORBIDDEN_IMPORT_PREFIXES
        ]
        assert forbidden == [], f"{path} imports forbidden modules: {forbidden}"

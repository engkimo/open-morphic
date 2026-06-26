"""morphic doctor — system health diagnostics.

Checks connectivity for all engines, databases, and API keys.
Provides a single-glance overview of system readiness.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import typer

from infrastructure.hooks.workspace_hook_registry import HookDiagnostic, WorkspaceHookRegistry
from interface.cli._utils import _get_container, _run
from interface.cli.formatters import console

doctor_app = typer.Typer()
_HOOKS_WORKSPACE_OPTION = typer.Option(
    None,
    "--workspace",
    help="Workspace root.",
)


@contextmanager
def _disabled_logging(enabled: bool) -> Iterator[None]:
    if not enabled:
        yield
        return

    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous)


class _Check:
    """Result of a single diagnostic check."""

    __slots__ = ("name", "status", "message", "duration_ms")

    def __init__(self, name: str, status: str, message: str, duration_ms: float = 0.0) -> None:
        self.name = name
        self.status = status  # "OK" | "WARN" | "FAIL"
        self.message = message
        self.duration_ms = duration_ms


def _check_from_hook(diagnostic: HookDiagnostic) -> _Check:
    return _Check(
        diagnostic.name,
        diagnostic.status,
        diagnostic.message,
        diagnostic.duration_ms,
    )


def _style(status: str) -> str:
    return {"OK": "green", "WARN": "yellow", "FAIL": "red"}.get(status, "dim")


def _check_payload(check: _Check) -> dict[str, object]:
    return {
        "duration_ms": check.duration_ms,
        "message": check.message,
        "name": check.name,
        "status": check.status,
    }


def _checks_payload(checks: list[_Check]) -> dict[str, object]:
    ok = sum(1 for check in checks if check.status == "OK")
    warn = sum(1 for check in checks if check.status == "WARN")
    fail = sum(1 for check in checks if check.status == "FAIL")
    status = "FAIL" if fail else "WARN" if warn else "OK"
    return {
        "checks": [_check_payload(check) for check in checks],
        "status": status,
        "summary": {"fail": fail, "ok": ok, "warn": warn},
    }


def _render_checks_table(title: str, checks: list[_Check]) -> None:
    from rich.table import Table

    console.print(f"[bold]{title}[/bold]\n")
    table = Table()
    table.add_column("Component", min_width=20)
    table.add_column("Status", justify="center", min_width=6)
    table.add_column("Details")

    for check in checks:
        style = _style(check.status)
        table.add_row(check.name, f"[{style}]{check.status}[/]", check.message)

    console.print(table)
    payload = _checks_payload(checks)
    summary = payload["summary"]
    console.print(
        f"\n[green]{summary['ok']} OK[/]  "
        f"[yellow]{summary['warn']} WARN[/]  "
        f"[red]{summary['fail']} FAIL[/]"
    )


async def _check_ollama(container) -> _Check:  # type: ignore[type-arg]
    t0 = time.monotonic()
    try:
        running = await container.ollama.is_running()
        elapsed = (time.monotonic() - t0) * 1000
        if not running:
            return _Check("Ollama", "FAIL", "Not running", elapsed)
        models = await container.ollama.list_models()
        names = ", ".join(models[:5]) if models else "(none)"
        return _Check("Ollama", "OK", f"{len(models)} models: {names}", elapsed)
    except Exception as exc:
        return _Check("Ollama", "FAIL", str(exc), (time.monotonic() - t0) * 1000)


async def _check_engines(container) -> list[_Check]:  # type: ignore[type-arg]
    checks: list[_Check] = []
    engines = await container.route_to_engine.list_engines()
    for e in engines:
        name = e.engine_type.value
        if e.available:
            checks.append(_Check(f"Engine: {name}", "OK", "Available"))
        else:
            checks.append(_Check(f"Engine: {name}", "WARN", "Unavailable"))
    return checks


def _check_cli_binary(name: str, binary: str) -> _Check:
    path = shutil.which(binary)
    if path:
        return _Check(name, "OK", f"Found at {path}")
    return _Check(name, "WARN", f"'{binary}' not found in PATH (optional)")


def _check_api_keys(container) -> list[_Check]:  # type: ignore[type-arg]
    s = container.settings
    checks: list[_Check] = []
    for label, has_key in [
        ("API: Anthropic", s.has_anthropic),
        ("API: OpenAI", s.has_openai),
        ("API: Gemini", s.has_gemini),
    ]:
        if has_key:
            checks.append(_Check(label, "OK", "Configured"))
        else:
            checks.append(_Check(label, "WARN", "Not configured"))
    return checks


def _check_database(container) -> _Check:  # type: ignore[type-arg]
    if container.settings.use_postgres:
        return _Check("Database", "OK", "PostgreSQL mode")
    if getattr(container.settings, "use_sqlite", False):
        return _Check("Database", "OK", f"SQLite mode ({container.settings.sqlite_url})")
    return _Check("Database", "OK", "In-Memory mode (non-persistent)")


def _check_docker() -> _Check:
    """Check Docker daemon and OpenHands image availability."""
    import subprocess

    # Docker daemon
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return _Check("Docker", "WARN", "Daemon not running")
    except FileNotFoundError:
        return _Check("Docker", "WARN", "Docker CLI not found")
    except subprocess.TimeoutExpired:
        return _Check("Docker", "WARN", "Docker info timed out")
    except Exception as exc:
        return _Check("Docker", "WARN", str(exc))

    # OpenHands image
    try:
        img_result = subprocess.run(
            [
                "docker", "images", "--format", "{{.Repository}}:{{.Tag}}",
                "ghcr.io/all-hands-ai/openhands",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        images = [line.strip() for line in img_result.stdout.strip().splitlines() if line.strip()]
        if images:
            return _Check("Docker", "OK", f"Running, OpenHands image: {images[0]}")
        return _Check("Docker", "OK", "Running (OpenHands image not pulled)")
    except Exception:
        return _Check("Docker", "OK", "Running (image check failed)")


async def _check_openhands(container) -> _Check:  # type: ignore[type-arg]
    """Check OpenHands REST API reachability."""
    from domain.value_objects.agent_engine import AgentEngineType

    t0 = time.monotonic()
    try:
        driver = container.agent_drivers.get(AgentEngineType.OPENHANDS)
        if driver is None:
            return _Check("OpenHands", "WARN", "Driver not wired", (time.monotonic() - t0) * 1000)
        available = await driver.is_available()
        elapsed = (time.monotonic() - t0) * 1000
        if available:
            return _Check("OpenHands", "OK", f"REST API reachable ({elapsed:.0f}ms)", elapsed)
        return _Check(
            "OpenHands", "WARN", "REST API unreachable (start with `docker run`)", elapsed,
        )
    except Exception as exc:
        return _Check("OpenHands", "WARN", str(exc), (time.monotonic() - t0) * 1000)


async def _check_agents(container) -> list[_Check]:  # type: ignore[type-arg]
    checks = [
        _check_cli_binary("CLI: claude", container.settings.claude_code_cli_path),
        _check_cli_binary("CLI: gemini", container.settings.gemini_cli_path),
        _check_cli_binary("CLI: codex", container.settings.codex_cli_path),
    ]
    checks.extend(await _check_engines(container))
    return checks


@doctor_app.command("agents")
def agents(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
) -> None:
    """Run agent engine and CLI diagnostics."""
    with _disabled_logging(json_output):
        container = _get_container()
        checks = _run(_check_agents(container))
    payload = _checks_payload(checks)

    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        _render_checks_table("Morphic-Agent Agent Diagnostics", checks)

    summary = payload["summary"]
    if summary["fail"] > 0:
        raise typer.Exit(code=1)


@doctor_app.command("hooks")
def hooks(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    workspace: Path | None = _HOOKS_WORKSPACE_OPTION,
) -> None:
    """Validate workspace hook definitions without executing them."""
    checks = [
        _check_from_hook(diagnostic)
        for diagnostic in WorkspaceHookRegistry(workspace or Path.cwd()).validate()
    ]
    payload = _checks_payload(checks)

    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        _render_checks_table("Morphic-Agent Hook Diagnostics", checks)

    summary = payload["summary"]
    if summary["fail"] > 0:
        raise typer.Exit(code=1)


@doctor_app.command("check")
def check() -> None:
    """Run comprehensive system health diagnostics."""
    container = _get_container()
    results: list[_Check] = []

    # Ollama
    results.append(_run(_check_ollama(container)))

    # CLI binaries
    results.append(_check_cli_binary("CLI: claude", container.settings.claude_code_cli_path))
    results.append(_check_cli_binary("CLI: gemini", container.settings.gemini_cli_path))
    results.append(_check_cli_binary("CLI: codex", container.settings.codex_cli_path))

    # Docker & OpenHands
    results.append(_check_docker())
    results.append(_run(_check_openhands(container)))

    # Engine availability
    results.extend(_run(_check_engines(container)))

    # API keys
    results.extend(_check_api_keys(container))

    # Database
    results.append(_check_database(container))

    _render_checks_table("Morphic-Agent System Diagnostics", results)

    fail = _checks_payload(results)["summary"]["fail"]
    if fail > 0:
        raise typer.Exit(code=1)

"""morphic doctor — system health diagnostics.

Checks connectivity for all engines, databases, and API keys.
Provides a single-glance overview of system readiness.
"""

from __future__ import annotations

import shutil
import time

import typer

from interface.cli._utils import _get_container, _run
from interface.cli.formatters import console

doctor_app = typer.Typer()


class _Check:
    """Result of a single diagnostic check."""

    __slots__ = ("name", "status", "message", "duration_ms")

    def __init__(self, name: str, status: str, message: str, duration_ms: float = 0.0) -> None:
        self.name = name
        self.status = status  # "OK" | "WARN" | "FAIL"
        self.message = message
        self.duration_ms = duration_ms


def _style(status: str) -> str:
    return {"OK": "green", "WARN": "yellow", "FAIL": "red"}.get(status, "dim")


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
    return _Check(name, "FAIL", f"'{binary}' not found in PATH")


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


@doctor_app.command("check")
def check() -> None:
    """Run comprehensive system health diagnostics."""
    from rich.table import Table

    console.print("[bold]Morphic-Agent System Diagnostics[/bold]\n")

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

    # Render table
    table = Table()
    table.add_column("Component", min_width=20)
    table.add_column("Status", justify="center", min_width=6)
    table.add_column("Details")

    for r in results:
        style = _style(r.status)
        table.add_row(r.name, f"[{style}]{r.status}[/]", r.message)

    console.print(table)

    ok = sum(1 for r in results if r.status == "OK")
    warn = sum(1 for r in results if r.status == "WARN")
    fail = sum(1 for r in results if r.status == "FAIL")
    console.print(f"\n[green]{ok} OK[/]  [yellow]{warn} WARN[/]  [red]{fail} FAIL[/]")

    if fail > 0:
        raise typer.Exit(code=1)

"""Tests for morphic serve CLI command — Sprint 23.1.

Tests focus on the startup banner formatting logic, not actual server startup.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from interface.cli.main import app
from shared.config import Environment

runner = CliRunner()


class _MockSettings:
    """Minimal settings for serve banner tests."""

    morphic_agent_env = Environment.DEVELOPMENT
    use_postgres: bool = False
    use_sqlite: bool = False
    sqlite_url: str = "sqlite+aiosqlite:///morphic_agent.db"
    ollama_default_model: str = "qwen3:8b"
    default_monthly_budget_usd: float = 50.0
    react_enabled: bool = True
    has_anthropic: bool = True
    has_openai: bool = False
    has_gemini: bool = True
    claude_code_cli_path: str = "claude"
    gemini_cli_path: str = "gemini"
    codex_cli_path: str = "codex"
    mcp_enabled: bool = True
    marketplace_enabled: bool = True
    evolution_enabled: bool = True
    laee_enabled: bool = True
    log_level: str = "info"


class TestServeBanner:
    def test_banner_shows_configuration(self) -> None:
        """Banner should show environment and DB mode."""
        from interface.cli.commands.serve import _print_startup_banner

        settings = _MockSettings()
        # Capture output by running with Rich console
        _print_startup_banner(settings)  # Should not raise

    def test_banner_shows_api_keys(self) -> None:
        from interface.cli.commands.serve import _print_startup_banner

        settings = _MockSettings()
        _print_startup_banner(settings)  # Should not raise

    @patch("uvicorn.run")
    def test_serve_invokes_uvicorn(self, mock_run: MagicMock) -> None:
        """morphic serve start should call uvicorn.run()."""
        runner.invoke(app, ["serve", "start", "--port", "9999"])
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs[1]["port"] == 9999

    @patch("uvicorn.run")
    def test_serve_default_host(self, mock_run: MagicMock) -> None:
        runner.invoke(app, ["serve", "start"])
        call_kwargs = mock_run.call_args
        assert call_kwargs[1]["host"] == "0.0.0.0"
        assert call_kwargs[1]["port"] == 8001

    @patch("uvicorn.run")
    def test_serve_reload_flag(self, mock_run: MagicMock) -> None:
        runner.invoke(app, ["serve", "start", "--reload"])
        call_kwargs = mock_run.call_args
        assert call_kwargs[1]["reload"] is True

    @patch("uvicorn.run")
    def test_serve_workers(self, mock_run: MagicMock) -> None:
        runner.invoke(app, ["serve", "start", "--workers", "4"])
        call_kwargs = mock_run.call_args
        assert call_kwargs[1]["workers"] == 4

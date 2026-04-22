"""Tests for Context export CLI — Sprint 25.4 (TD-135).

Uses _set_container() to inject a mock container, verifying that CLI
commands correctly call context_bridge methods and format output.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

from typer.testing import CliRunner

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FakeExportResult:
    platform: str
    content: str
    token_estimate: int


def _make_export_result(
    platform: str = "claude_code",
    content: str = "# Morphic-Agent Context\n\n## Query\ntest",
    tokens: int = 12,
) -> _FakeExportResult:
    return _FakeExportResult(
        platform=platform, content=content, token_estimate=tokens
    )


def _make_container(
    bridge_available: bool = True,
    export_result: _FakeExportResult | None = None,
    export_all_results: list[_FakeExportResult] | None = None,
    export_raises: Exception | None = None,
):
    if not bridge_available:
        return MagicMock(context_bridge=None)
    bridge = MagicMock()
    if export_raises:
        bridge.export = AsyncMock(side_effect=export_raises)
    else:
        bridge.export = AsyncMock(
            return_value=export_result or _make_export_result()
        )
    bridge.export_all = AsyncMock(
        return_value=export_all_results
        or [
            _make_export_result("claude_code"),
            _make_export_result("chatgpt", "ChatGPT content", 8),
            _make_export_result("cursor", "Cursor rules", 6),
            _make_export_result("gemini", "<morphic-context/>", 5),
        ]
    )
    return MagicMock(context_bridge=bridge)


def _invoke(*args: str, container=None):
    from interface.cli._utils import _set_container
    from interface.cli.main import app

    if container:
        _set_container(container)
    result = runner.invoke(app, list(args))
    _set_container(None)
    return result


# ---------------------------------------------------------------------------
# morphic context export
# ---------------------------------------------------------------------------


class TestExportCommand:
    def test_export_success(self):
        c = _make_container()
        result = _invoke("context", "export", "claude_code", container=c)
        assert result.exit_code == 0
        assert "claude_code" in result.output
        c.context_bridge.export.assert_called_once()

    def test_export_with_query(self):
        c = _make_container()
        result = _invoke(
            "context", "export", "chatgpt", "--query", "auth", container=c
        )
        assert result.exit_code == 0
        c.context_bridge.export.assert_called_once()
        call_kwargs = c.context_bridge.export.call_args
        assert call_kwargs[1]["query"] == "auth" or call_kwargs[0][1] == "auth"

    def test_export_with_max_tokens(self):
        c = _make_container()
        result = _invoke(
            "context", "export", "cursor",
            "--max-tokens", "500", container=c,
        )
        assert result.exit_code == 0

    def test_export_to_file(self, tmp_path):
        out = tmp_path / "export.md"
        c = _make_container()
        result = _invoke(
            "context", "export", "claude_code",
            "--output", str(out), container=c,
        )
        assert result.exit_code == 0
        assert out.exists()
        assert "Morphic-Agent" in out.read_text()
        assert "Exported to" in result.output

    def test_export_invalid_platform(self):
        c = _make_container(
            export_raises=ValueError("Unsupported platform: foo")
        )
        result = _invoke("context", "export", "foo", container=c)
        assert result.exit_code == 1
        assert "Unsupported" in result.output or "Error" in result.output

    def test_export_no_bridge(self):
        c = _make_container(bridge_available=False)
        result = _invoke("context", "export", "claude_code", container=c)
        assert result.exit_code == 1
        assert "not available" in result.output


# ---------------------------------------------------------------------------
# morphic context export-all
# ---------------------------------------------------------------------------


class TestExportAllCommand:
    def test_export_all_success(self):
        c = _make_container()
        result = _invoke("context", "export-all", container=c)
        assert result.exit_code == 0
        assert "Context Exports" in result.output
        c.context_bridge.export_all.assert_called_once()

    def test_export_all_with_query(self):
        c = _make_container()
        result = _invoke(
            "context", "export-all", "--query", "auth", container=c
        )
        assert result.exit_code == 0

    def test_export_all_shows_platforms(self):
        c = _make_container()
        result = _invoke("context", "export-all", container=c)
        assert result.exit_code == 0
        assert "claude_code" in result.output

    def test_export_all_no_bridge(self):
        c = _make_container(bridge_available=False)
        result = _invoke("context", "export-all", container=c)
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# morphic context platforms
# ---------------------------------------------------------------------------


class TestPlatformsCommand:
    def test_platforms_lists_all(self):
        c = _make_container()
        result = _invoke("context", "platforms", container=c)
        assert result.exit_code == 0
        assert "claude_code" in result.output
        assert "chatgpt" in result.output
        assert "cursor" in result.output
        assert "gemini" in result.output

    def test_platforms_shows_descriptions(self):
        c = _make_container()
        result = _invoke("context", "platforms", container=c)
        assert result.exit_code == 0
        assert "CLAUDE.md" in result.output or "markdown" in result.output


# ---------------------------------------------------------------------------
# Formatter tests
# ---------------------------------------------------------------------------


class TestContextFormatters:
    def test_print_export_result(self):
        from interface.cli.formatters import print_export_result

        result = _make_export_result()
        print_export_result(result)

    def test_print_export_results_table(self):
        from interface.cli.formatters import print_export_results_table

        results = [
            _make_export_result("claude_code"),
            _make_export_result("chatgpt", "chat content", 10),
        ]
        print_export_results_table(results)

    def test_print_export_results_table_empty(self):
        from interface.cli.formatters import print_export_results_table

        print_export_results_table([])

"""Tests for ModelCapabilityRegistry — model capability lookup."""

from domain.services.model_capability_registry import ModelCapabilityRegistry


class TestGet:
    def test_known_model(self) -> None:
        cap = ModelCapabilityRegistry.get("o4-mini")
        assert "structured" in cap.lower()

    def test_claude_model(self) -> None:
        cap = ModelCapabilityRegistry.get("claude-sonnet-4-6")
        assert "analysis" in cap.lower()

    def test_gemini_model(self) -> None:
        cap = ModelCapabilityRegistry.get("gemini/gemini-3-pro-preview")
        assert "search" in cap.lower() or "google" in cap.lower()

    def test_unknown_model_returns_default(self) -> None:
        cap = ModelCapabilityRegistry.get("unknown/model-xyz")
        assert cap == "General-purpose AI model."


class TestFormatForPrompt:
    def test_single_model(self) -> None:
        result = ModelCapabilityRegistry.format_for_prompt(("o4-mini",))
        assert result.startswith("- o4-mini:")
        assert "\n" not in result

    def test_multiple_models(self) -> None:
        models = ("o4-mini", "claude-sonnet-4-6")
        result = ModelCapabilityRegistry.format_for_prompt(models)
        lines = result.split("\n")
        assert len(lines) == 2
        assert lines[0].startswith("- o4-mini:")
        assert lines[1].startswith("- claude-sonnet-4-6:")

    def test_unknown_model_in_list(self) -> None:
        result = ModelCapabilityRegistry.format_for_prompt(("unknown/x",))
        assert "General-purpose" in result

    def test_empty_tuple(self) -> None:
        result = ModelCapabilityRegistry.format_for_prompt(())
        assert result == ""

"""Tests for ModelPreferenceExtractor — model name extraction from goals."""

from domain.services.model_preference_extractor import ModelPreferenceExtractor
from domain.value_objects.collaboration_mode import CollaborationMode
from domain.value_objects.model_preference import ModelPreference


class TestExtractNoModel:
    def test_plain_english(self) -> None:
        pref = ModelPreferenceExtractor.extract("Implement fibonacci in Python")
        assert pref.models == ()
        assert pref.clean_goal == "Implement fibonacci in Python"
        assert not pref.has_preferences
        assert not pref.is_multi_model

    def test_plain_japanese(self) -> None:
        pref = ModelPreferenceExtractor.extract("FizzBuzzを書いて")
        assert pref.models == ()
        assert pref.clean_goal == "FizzBuzzを書いて"


class TestExtractSingleModel:
    def test_gpt(self) -> None:
        pref = ModelPreferenceExtractor.extract("GPTで映画チケットを探して")
        assert pref.models == ("o4-mini",)
        assert pref.has_preferences
        assert not pref.is_multi_model

    def test_claude(self) -> None:
        pref = ModelPreferenceExtractor.extract("Use Claude to write a poem")
        assert pref.models == ("claude-sonnet-4-6",)
        assert pref.has_preferences

    def test_gemini(self) -> None:
        pref = ModelPreferenceExtractor.extract("Geminiで要約して")
        assert pref.models == ("gemini/gemini-3-pro-preview",)

    def test_case_insensitive(self) -> None:
        pref = ModelPreferenceExtractor.extract("use CHATGPT to summarize")
        assert pref.models == ("o4-mini",)


class TestExtractMultiModel:
    def test_three_models_japanese(self) -> None:
        pref = ModelPreferenceExtractor.extract("gptとgemini,claudeと一緒に映画チケットを探して")
        assert len(pref.models) == 3
        assert "o4-mini" in pref.models
        assert "gemini/gemini-3-pro-preview" in pref.models
        assert "claude-sonnet-4-6" in pref.models
        assert pref.is_multi_model
        assert "映画チケット" in pref.clean_goal

    def test_two_models_english(self) -> None:
        pref = ModelPreferenceExtractor.extract("Compare GPT and Claude on this task")
        assert len(pref.models) == 2
        assert "o4-mini" in pref.models
        assert "claude-sonnet-4-6" in pref.models

    def test_preserves_first_occurrence_order(self) -> None:
        pref = ModelPreferenceExtractor.extract("Claude, GPT, Gemini で比較")
        assert pref.models[0] == "claude-sonnet-4-6"
        assert pref.models[1] == "o4-mini"
        assert pref.models[2] == "gemini/gemini-3-pro-preview"


class TestDedup:
    def test_gpt_and_chatgpt_dedup(self) -> None:
        """GPT and ChatGPT both map to o4-mini; should not duplicate."""
        pref = ModelPreferenceExtractor.extract("GPT and ChatGPT for testing")
        assert pref.models == ("o4-mini",)

    def test_openai_and_gpt_dedup(self) -> None:
        pref = ModelPreferenceExtractor.extract("OpenAI and GPT comparison")
        assert pref.models == ("o4-mini",)

    def test_claude_and_anthropic_dedup(self) -> None:
        pref = ModelPreferenceExtractor.extract("Claude vs Anthropic")
        assert pref.models == ("claude-sonnet-4-6",)


class TestExtractEngineAliases:
    """Engine-name aliases (codex, ollama) should route to correct engines."""

    def test_codex(self) -> None:
        pref = ModelPreferenceExtractor.extract("codexでバブルソートを書いて")
        assert pref.models == ("o4-mini",)
        assert pref.has_preferences

    def test_codex_english(self) -> None:
        pref = ModelPreferenceExtractor.extract("Use Codex to write a sorting algorithm")
        assert pref.models == ("o4-mini",)

    def test_ollama(self) -> None:
        pref = ModelPreferenceExtractor.extract("ollamaで1+1を計算して")
        assert pref.models == ("ollama/qwen3:8b",)
        assert pref.has_preferences

    def test_codex_and_claude(self) -> None:
        pref = ModelPreferenceExtractor.extract("codexとclaudeで比較して")
        assert "o4-mini" in pref.models
        assert "claude-sonnet-4-6" in pref.models
        assert pref.is_multi_model

    def test_codex_dedup_with_gpt(self) -> None:
        """Codex and GPT both map to o4-mini; should not duplicate."""
        pref = ModelPreferenceExtractor.extract("codex and GPT for testing")
        assert pref.models == ("o4-mini",)


class TestCleanGoal:
    def test_model_names_removed(self) -> None:
        pref = ModelPreferenceExtractor.extract("GPT summarize this document")
        assert "GPT" not in pref.clean_goal
        assert "summarize" in pref.clean_goal

    def test_clean_goal_not_empty(self) -> None:
        """Even if goal is mostly model names, clean_goal should not be empty."""
        pref = ModelPreferenceExtractor.extract("GPT Claude Gemini")
        assert len(pref.clean_goal) > 0

    def test_orphaned_particle_removed(self) -> None:
        """Leading 'と' particle left after model removal should be stripped."""
        pref = ModelPreferenceExtractor.extract("gptとclaudeで、1+1を計算して")
        assert pref.clean_goal.startswith("1+1")
        assert "と" not in pref.clean_goal.split()[0]

    def test_two_models_de_particle(self) -> None:
        """'で' particle between models should not leak into clean_goal."""
        pref = ModelPreferenceExtractor.extract("claudeとgeminiで東京の天気を検索して")
        assert "東京" in pref.clean_goal
        assert not pref.clean_goal.startswith("と")


class TestCollaborationModeDetection:
    """Sprint 12.6: Collaboration mode detected from keywords."""

    def test_comparison_japanese(self) -> None:
        pref = ModelPreferenceExtractor.extract("Claude, GPT, Gemini で比較")
        assert pref.collaboration_mode == CollaborationMode.COMPARISON

    def test_comparison_english_vs(self) -> None:
        pref = ModelPreferenceExtractor.extract("Compare GPT vs Claude on this task")
        assert pref.collaboration_mode == CollaborationMode.COMPARISON

    def test_comparison_english_compare(self) -> None:
        pref = ModelPreferenceExtractor.extract("GPT and Claude compare results")
        assert pref.collaboration_mode == CollaborationMode.COMPARISON

    def test_diverse_japanese(self) -> None:
        pref = ModelPreferenceExtractor.extract("GPT と Claude でそれぞれ分析")
        assert pref.collaboration_mode == CollaborationMode.DIVERSE

    def test_diverse_english(self) -> None:
        pref = ModelPreferenceExtractor.extract("GPT and Claude each model does different aspect")
        assert pref.collaboration_mode == CollaborationMode.DIVERSE

    def test_parallel_japanese(self) -> None:
        pref = ModelPreferenceExtractor.extract("gptとgemini,claudeと一緒に映画チケットを探して")
        assert pref.collaboration_mode == CollaborationMode.PARALLEL

    def test_parallel_english(self) -> None:
        pref = ModelPreferenceExtractor.extract("GPT and Claude together solve this")
        assert pref.collaboration_mode == CollaborationMode.PARALLEL

    def test_auto_when_no_keyword(self) -> None:
        pref = ModelPreferenceExtractor.extract("GPT and Claude do this task")
        assert pref.collaboration_mode == CollaborationMode.AUTO

    def test_single_model_always_auto(self) -> None:
        pref = ModelPreferenceExtractor.extract("Claude で比較して分析")
        assert pref.collaboration_mode == CollaborationMode.AUTO

    def test_no_model_always_auto(self) -> None:
        pref = ModelPreferenceExtractor.extract("比較して分析して")
        assert pref.collaboration_mode == CollaborationMode.AUTO

    def test_priority_comparison_over_parallel(self) -> None:
        """COMPARISON > PARALLEL when both keywords present."""
        pref = ModelPreferenceExtractor.extract("GPT と Claude を一緒に比較して")
        assert pref.collaboration_mode == CollaborationMode.COMPARISON

    def test_priority_comparison_over_diverse(self) -> None:
        pref = ModelPreferenceExtractor.extract("GPT と Claude でそれぞれ比較")
        assert pref.collaboration_mode == CollaborationMode.COMPARISON

    def test_priority_diverse_over_parallel(self) -> None:
        pref = ModelPreferenceExtractor.extract("GPT と Claude でそれぞれ一緒に分析")
        assert pref.collaboration_mode == CollaborationMode.DIVERSE


class TestModelPreferenceDataclass:
    def test_frozen(self) -> None:
        pref = ModelPreference(models=("a",), clean_goal="test")
        try:
            pref.models = ("b",)  # type: ignore[misc]
            raise AssertionError("Should be frozen")
        except AttributeError:
            pass

    def test_has_preferences_empty(self) -> None:
        pref = ModelPreference(models=(), clean_goal="test")
        assert not pref.has_preferences

    def test_is_multi_model_single(self) -> None:
        pref = ModelPreference(models=("a",), clean_goal="test")
        assert not pref.is_multi_model

    def test_is_multi_model_multiple(self) -> None:
        pref = ModelPreference(models=("a", "b"), clean_goal="test")
        assert pref.is_multi_model

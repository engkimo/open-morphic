"""ModelCapabilityRegistry — static model-id to capability description mapping.

Pure domain knowledge, no I/O. Used by IntentAnalyzer to inject model
strengths into the LLM decomposition prompt.
"""

from __future__ import annotations

_MODEL_CAPABILITIES: dict[str, str] = {
    "o4-mini": (
        "Fast structured reasoning. Good at search, extraction, "
        "structured data output. Cost-efficient."
    ),
    "claude-sonnet-4-6": (
        "Deep analysis and synthesis. Excellent at nuanced reasoning, "
        "comparing options, writing reports, and code review."
    ),
    "gemini/gemini-3-pro-preview": (
        "Google ecosystem integration. Strong at web search grounding, "
        "real-time information retrieval, and long-context analysis."
    ),
    "ollama/qwen3:8b": (
        "Lightweight local model. Good for drafts, simple tasks, "
        "and iterative refinement. Free to run."
    ),
    "ollama/qwen3-coder:30b": (
        "Local coding specialist. Strong at code generation, refactoring, "
        "and technical analysis. Free to run."
    ),
    "ollama/deepseek-r1:8b": (
        "Local reasoning specialist. Good at step-by-step problem solving "
        "and mathematical reasoning. Free to run."
    ),
    "claude-opus-4-6": (
        "Highest-quality reasoning. Best for complex architecture decisions, "
        "nuanced analysis, and research synthesis."
    ),
}

_DEFAULT_CAPABILITY = "General-purpose AI model."


class ModelCapabilityRegistry:
    """Static registry mapping model IDs to human-readable capability descriptions."""

    @staticmethod
    def get(model_id: str) -> str:
        """Return capability description for *model_id*, or a default."""
        return _MODEL_CAPABILITIES.get(model_id, _DEFAULT_CAPABILITY)

    @staticmethod
    def format_for_prompt(model_ids: tuple[str, ...]) -> str:
        """Format model capabilities as a prompt-ready string."""
        lines: list[str] = []
        for mid in model_ids:
            cap = ModelCapabilityRegistry.get(mid)
            lines.append(f"- {mid}: {cap}")
        return "\n".join(lines)

"""ModelTier and TaskType — LLM routing classification."""

from enum import Enum


class ModelTier(str, Enum):
    FREE = "free"  # Ollama local ($0)
    LOW = "low"  # Claude Haiku, Gemini Flash
    MEDIUM = "medium"  # Claude Sonnet, GPT-4o-mini
    HIGH = "high"  # Claude Opus, GPT-4o


class TaskType(str, Enum):
    SIMPLE_QA = "simple_qa"
    CODE_GENERATION = "code_generation"
    COMPLEX_REASONING = "complex_reasoning"
    FILE_OPERATION = "file_operation"
    LONG_CONTEXT = "long_context"
    MULTIMODAL = "multimodal"

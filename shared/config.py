"""Morphic-Agent configuration — pydantic-settings based.

Cross-cutting concern: used by infrastructure and interface layers.
Domain layer NEVER imports this directly (uses dependency injection instead).
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class PlanningMode(str, Enum):
    INTERACTIVE = "interactive"
    AUTO = "auto"
    DISABLED = "disabled"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM APIs ──
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_gemini_api_key: str = ""

    # ── Ollama ──
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_default_model: str = "qwen3-coder:30b"
    ollama_coding_model: str = "qwen3-coder:30b"
    local_first: bool = True

    # ── Agent CLI ──
    openhands_base_url: str = "http://localhost:3000"
    openhands_model: str = "claude-sonnet-4-6"
    claude_code_sdk_enabled: bool = True
    gemini_cli_enabled: bool = True
    codex_cli_enabled: bool = True
    agent_default_engine: str = "claude_code"

    # ── Database ──
    database_url: str = "postgresql+asyncpg://morphic:morphic_dev@localhost:5432/morphic_agent"
    database_url_sync: str = "postgresql://morphic:morphic_dev@localhost:5432/morphic_agent"
    use_postgres: bool = False
    redis_url: str = "redis://localhost:6379"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "morphic_dev"

    # ── Celery ──
    celery_enabled: bool = False
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # ── Memory ──
    semantic_memory_backend: str = "mem0"
    mem0_api_key: str = ""
    memory_target_tokens: int = 800
    memory_retention_threshold: float = 0.3

    # ── Embedding (Semantic Fingerprint) ──
    embedding_backend: str = "ollama"  # ollama | none
    embedding_model: str = "all-minilm"
    embedding_dimensions: int = 384
    embedding_lsh_seed: int = 42
    embedding_lsh_n_planes: int = 32

    # ── Cost ──
    default_monthly_budget_usd: float = 50.0
    default_task_budget_usd: float = 1.0
    auto_downgrade_on_budget: bool = True
    cache_breakpoints_enabled: bool = True

    # ── LAEE ──
    laee_enabled: bool = True
    laee_approval_mode: str = "confirm-destructive"
    laee_audit_log_path: Path = Path(".morphic/audit_log.jsonl")
    laee_undo_enabled: bool = True
    laee_max_concurrent_shells: int = 10
    laee_browser_headless: bool = True
    laee_gui_enabled: bool = True
    laee_cron_enabled: bool = True

    # ── Context Engineering ──
    context_todo_path: Path = Path("todo.md")
    context_cache_dir: Path = Path(".morphic/cache")

    # ── General ──
    morphic_agent_env: Environment = Environment.DEVELOPMENT
    auto_tool_install: bool = False
    evolution_enabled: bool = True
    planning_mode: PlanningMode = PlanningMode.INTERACTIVE

    @property
    def is_development(self) -> bool:
        return self.morphic_agent_env == Environment.DEVELOPMENT

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_gemini(self) -> bool:
        return bool(self.google_gemini_api_key)


settings = Settings()

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
    ollama_default_model: str = "qwen3:8b"
    ollama_coding_model: str = "qwen3:8b"
    local_first: bool = True

    # ── Agent CLI ──
    openhands_base_url: str = "http://localhost:3000"
    openhands_model: str = "claude-sonnet-4-6"
    openhands_api_key: str = ""
    claude_code_sdk_enabled: bool = True
    claude_code_cli_path: str = "claude"
    gemini_cli_enabled: bool = True
    gemini_cli_path: str = "gemini"
    codex_cli_enabled: bool = True
    codex_cli_path: str = "codex"
    adk_enabled: bool = True
    adk_default_model: str = "gemini-2.5-flash"
    agent_default_engine: str = "claude_code"

    # ── Database ──
    database_url: str = "postgresql+asyncpg://morphic:morphic_dev@localhost:5432/morphic_agent"
    database_url_sync: str = "postgresql://morphic:morphic_dev@localhost:5432/morphic_agent"
    use_postgres: bool = False
    use_sqlite: bool = False
    sqlite_url: str = "sqlite+aiosqlite:///morphic_agent.db"
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

    # ── Semantic Dedup ──
    semantic_dedup_enabled: bool = True
    semantic_dedup_threshold: float = 0.85
    token_dedup_threshold: float = 0.6  # Jaccard word-overlap for paraphrase detection

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

    # ── Fractal Engine ──
    execution_engine: str = "langgraph"  # "langgraph" | "fractal"
    fractal_max_depth: int = 3
    fractal_candidates_per_node: int = 3
    fractal_plan_eval_models: str = ""  # comma-separated model list for Gate ①
    fractal_plan_eval_min_score: float = 0.5
    fractal_result_eval_ok_threshold: float = 0.7
    fractal_result_eval_retry_threshold: float = 0.4
    fractal_max_retries: int = 3
    fractal_max_plan_attempts: int = 2
    fractal_max_reflection_rounds: int = 2
    fractal_max_total_nodes: int = 20
    fractal_max_concurrent_nodes: int = 3  # 0 = unlimited; limits parallel asyncio.gather
    fractal_throttle_delay_ms: int = 0  # ms delay between node completions (CPU smoothing)
    fractal_max_execution_seconds: int = 180  # TD-181: hard time limit to prevent zombie tasks

    # ── ReAct Loop ──
    react_enabled: bool = True
    react_max_iterations: int = 10

    # ── Discussion ──
    discussion_max_rounds: int = 1  # 1 = single synthesis (backward compat), 2+ = iterative
    discussion_rotate_models: bool = True  # use different model each round
    discussion_role_assignment: bool = True  # LLM generates roles when user doesn't specify
    discussion_adaptive: bool = False  # adaptive round count based on convergence detection
    discussion_convergence_threshold: float = 0.85  # Jaccard similarity threshold for convergence
    discussion_min_rounds: int = 1  # minimum rounds before convergence check kicks in

    # ── Context Bridge ──
    context_bridge_default_tokens: int = 800

    # ── MCP ──
    mcp_enabled: bool = True
    mcp_transport: str = "stdio"
    mcp_port: int = 8100
    mcp_servers: str = "[]"  # JSON-encoded server configs

    # ── Marketplace ──
    marketplace_enabled: bool = True
    marketplace_auto_install: bool = False
    marketplace_safety_threshold: str = "experimental"  # verified | community | experimental
    mcp_registry_url: str = "https://registry.modelcontextprotocol.io"

    # ── Context Engineering ──
    context_todo_path: Path = Path("todo.md")
    context_cache_dir: Path = Path(".morphic/cache")

    # ── Affinity ──
    affinity_min_samples: int = 3
    affinity_boost_threshold: float = 0.6

    # ── Evolution ──
    evolution_enabled: bool = True
    evolution_strategy_dir: Path = Path(".morphic/evolution")
    evolution_auto_update: bool = True
    evolution_min_samples: int = 10

    # ── General ──
    morphic_agent_env: Environment = Environment.DEVELOPMENT
    auto_tool_install: bool = False
    planning_mode: PlanningMode = PlanningMode.INTERACTIVE
    planning_auto_approve_simple: bool = True
    log_level: str = "INFO"

    @property
    def marketplace_safety_threshold_tier(self):  # type: ignore[no-untyped-def]
        """Convert string threshold to SafetyTier enum."""
        from domain.value_objects.tool_safety import SafetyTier

        mapping = {
            "verified": SafetyTier.VERIFIED,
            "community": SafetyTier.COMMUNITY,
            "experimental": SafetyTier.EXPERIMENTAL,
            "unsafe": SafetyTier.UNSAFE,
        }
        return mapping.get(self.marketplace_safety_threshold.lower(), SafetyTier.EXPERIMENTAL)

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

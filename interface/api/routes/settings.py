"""Settings route — runtime configuration and system health."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from shared.config import Settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class FractalSettingsUpdate(BaseModel):
    """Mutable fractal engine settings (TD-175)."""

    max_depth: int | None = Field(default=None, ge=1, le=10)
    max_concurrent_nodes: int | None = Field(default=None, ge=0, le=50)
    throttle_delay_ms: int | None = Field(default=None, ge=0, le=10000)
    candidates_per_node: int | None = Field(default=None, ge=1, le=10)
    max_total_nodes: int | None = Field(default=None, ge=1, le=100)
    max_reflection_rounds: int | None = Field(default=None, ge=0, le=10)


def _safe_settings(s: Settings) -> dict:
    """Return settings dict with API keys redacted."""
    return {
        "version": "0.5.1",
        "environment": s.morphic_agent_env.value,
        "planning_mode": s.planning_mode.value,
        "local_first": s.local_first,
        "execution_engine": s.execution_engine,
        "budget": {
            "monthly_usd": s.default_monthly_budget_usd,
            "task_usd": s.default_task_budget_usd,
            "auto_downgrade": s.auto_downgrade_on_budget,
        },
        "ollama": {
            "base_url": s.ollama_base_url,
            "default_model": s.ollama_default_model,
        },
        "engines": {
            "claude_code_enabled": s.claude_code_sdk_enabled,
            "gemini_cli_enabled": s.gemini_cli_enabled,
            "codex_cli_enabled": s.codex_cli_enabled,
            "openhands_base_url": s.openhands_base_url,
            "default_engine": s.agent_default_engine,
        },
        "mcp": {
            "enabled": s.mcp_enabled,
            "transport": s.mcp_transport,
        },
        "laee": {
            "enabled": s.laee_enabled,
            "approval_mode": s.laee_approval_mode,
        },
        "api_keys_configured": {
            "anthropic": bool(s.anthropic_api_key),
            "openai": bool(s.openai_api_key),
            "gemini": bool(s.google_gemini_api_key),
        },
        "fractal": {
            "max_depth": s.fractal_max_depth,
            "candidates_per_node": s.fractal_candidates_per_node,
            "max_concurrent_nodes": s.fractal_max_concurrent_nodes,
            "throttle_delay_ms": s.fractal_throttle_delay_ms,
            "max_total_nodes": s.fractal_max_total_nodes,
            "max_reflection_rounds": s.fractal_max_reflection_rounds,
        },
    }


@router.get("")
async def get_settings(request: Request) -> dict:
    """Return current runtime settings (API keys redacted)."""
    container = request.app.state.container
    return _safe_settings(container.settings)


@router.put("/fractal")
async def update_fractal_settings(body: FractalSettingsUpdate, request: Request) -> dict:
    """Update fractal engine runtime settings (TD-175).

    Only non-null fields are applied.  Changes take effect on the *next*
    task execution — they mutate the shared ``Settings`` instance that
    ``AppContainer`` reads from.
    """
    container = request.app.state.container
    s = container.settings
    updated: dict[str, int] = {}

    for field_name, attr_name in (
        ("max_depth", "fractal_max_depth"),
        ("max_concurrent_nodes", "fractal_max_concurrent_nodes"),
        ("throttle_delay_ms", "fractal_throttle_delay_ms"),
        ("candidates_per_node", "fractal_candidates_per_node"),
        ("max_total_nodes", "fractal_max_total_nodes"),
        ("max_reflection_rounds", "fractal_max_reflection_rounds"),
    ):
        value = getattr(body, field_name)
        if value is not None:
            setattr(s, attr_name, value)
            updated[field_name] = value

    return {"updated": updated, "fractal": _safe_settings(s)["fractal"]}


@router.get("/health")
async def get_health(request: Request) -> dict:
    """Aggregated system health check."""
    container = request.app.state.container
    s = container.settings
    checks: list[dict] = []

    # Ollama check
    try:
        import httpx

        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{s.ollama_base_url}/api/tags")
            ollama_ok = resp.status_code == 200
    except Exception:
        ollama_ok = False
    checks.append({"name": "ollama", "status": "ok" if ollama_ok else "fail"})

    # Database check
    try:
        repo = container.task_repo
        db_ok = repo is not None
    except Exception:
        db_ok = False
    checks.append({"name": "database", "status": "ok" if db_ok else "fail"})

    # Engine availability summary
    for engine_name in ["claude_code", "gemini_cli", "codex_cli", "openhands"]:
        registry = getattr(container, "engine_registry", None)
        driver = registry.get(engine_name) if registry else None
        if driver:
            try:
                available = await driver.is_available()
                checks.append({"name": engine_name, "status": "ok" if available else "warn"})
            except Exception:
                checks.append({"name": engine_name, "status": "fail"})
        else:
            checks.append({"name": engine_name, "status": "skip"})

    overall = "ok" if all(c["status"] in ("ok", "skip") for c in checks) else "degraded"
    return {"overall": overall, "checks": checks}

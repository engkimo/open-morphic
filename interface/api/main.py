"""FastAPI application factory — HTTP + WebSocket interface."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from interface.api.container import AppContainer
from interface.api.routes.a2a import router as a2a_router
from interface.api.routes.benchmarks import router as benchmarks_router
from interface.api.routes.cognitive import router as cognitive_router
from interface.api.routes.cost import router as cost_router
from interface.api.routes.engines import router as engines_router
from interface.api.routes.evolution import router as evolution_router
from interface.api.routes.marketplace import router as marketplace_router
from interface.api.routes.memory import router as memory_router
from interface.api.routes.models import router as models_router
from interface.api.routes.plans import router as plans_router
from interface.api.routes.settings import router as settings_router
from interface.api.routes.task_stream import router as task_stream_router
from interface.api.routes.tasks import router as tasks_router
from interface.api.websocket import task_ws
from shared.config import Settings
from shared.logging import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create AppContainer on startup, teardown on shutdown."""
    s = Settings()
    setup_logging(s.log_level)

    # Export API keys to os.environ so LiteLLM can authenticate with cloud providers.
    # pydantic-settings reads .env but does NOT write to os.environ automatically.
    if s.anthropic_api_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", s.anthropic_api_key)
    if s.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", s.openai_api_key)
    if s.google_gemini_api_key:
        # LiteLLM expects GEMINI_API_KEY, not GOOGLE_GEMINI_API_KEY
        os.environ.setdefault("GEMINI_API_KEY", s.google_gemini_api_key)

    logger.info(
        "Morphic-Agent starting — env=%s log_level=%s",
        s.morphic_agent_env.value,
        s.log_level,
    )
    container = AppContainer(settings=s)
    await container.init()
    app.state.container = container
    logger.info("AppContainer initialized — planning_mode=%s", s.planning_mode.value)

    # TD-156: Log engine availability at startup for diagnostics
    try:
        statuses = await container.route_to_engine.list_engines()
        for st in statuses:
            tag = "✓" if st.available else "✗"
            logger.info(
                "Engine %s %s — available=%s",
                tag,
                st.engine_type.value,
                st.available,
            )
    except Exception:
        logger.warning("Failed to check engine availability at startup")

    yield
    logger.info("Morphic-Agent shutting down")
    await container.close()


def create_app(container: AppContainer | None = None) -> FastAPI:
    """Build the FastAPI app. Accepts optional container for testing."""
    app = FastAPI(
        title="Morphic-Agent",
        version="0.6.0",
        lifespan=lifespan if container is None else None,
    )

    # Inject pre-built container (testing)
    if container is not None:
        app.state.container = container

    # CORS for Next.js dev server + Chrome Extension (Context Bridge)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(http://localhost:\d+|chrome-extension://.+)$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # REST routes
    app.include_router(tasks_router)
    app.include_router(plans_router)
    app.include_router(a2a_router)
    app.include_router(models_router)
    app.include_router(cost_router)
    app.include_router(memory_router)
    app.include_router(engines_router)
    app.include_router(marketplace_router)
    app.include_router(evolution_router)
    app.include_router(cognitive_router)
    app.include_router(benchmarks_router)
    app.include_router(settings_router)
    app.include_router(task_stream_router)

    # WebSocket (legacy fallback)
    app.websocket("/ws/tasks/{task_id}")(task_ws)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

"""FastAPI application factory — HTTP + WebSocket interface."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from interface.api.container import AppContainer
from interface.api.routes.benchmarks import router as benchmarks_router
from interface.api.routes.cognitive import router as cognitive_router
from interface.api.routes.cost import router as cost_router
from interface.api.routes.engines import router as engines_router
from interface.api.routes.evolution import router as evolution_router
from interface.api.routes.marketplace import router as marketplace_router
from interface.api.routes.memory import router as memory_router
from interface.api.routes.models import router as models_router
from interface.api.routes.plans import router as plans_router
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
    logger.info(
        "Morphic-Agent starting — env=%s log_level=%s",
        s.morphic_agent_env.value, s.log_level,
    )
    container = AppContainer(settings=s)
    await container.init()
    app.state.container = container
    logger.info("AppContainer initialized — planning_mode=%s", s.planning_mode.value)
    yield
    logger.info("Morphic-Agent shutting down")
    await container.close()


def create_app(container: AppContainer | None = None) -> FastAPI:
    """Build the FastAPI app. Accepts optional container for testing."""
    app = FastAPI(
        title="Morphic-Agent",
        version="0.4.0-alpha",
        lifespan=lifespan if container is None else None,
    )

    # Inject pre-built container (testing)
    if container is not None:
        app.state.container = container

    # CORS for Next.js dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # REST routes
    app.include_router(tasks_router)
    app.include_router(plans_router)
    app.include_router(models_router)
    app.include_router(cost_router)
    app.include_router(memory_router)
    app.include_router(engines_router)
    app.include_router(marketplace_router)
    app.include_router(evolution_router)
    app.include_router(cognitive_router)
    app.include_router(benchmarks_router)

    # WebSocket
    app.websocket("/ws/tasks/{task_id}")(task_ws)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

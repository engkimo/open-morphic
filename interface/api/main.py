"""FastAPI application factory — HTTP + WebSocket interface."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from interface.api.container import AppContainer
from interface.api.routes.cost import router as cost_router
from interface.api.routes.memory import router as memory_router
from interface.api.routes.models import router as models_router
from interface.api.routes.plans import router as plans_router
from interface.api.routes.tasks import router as tasks_router
from interface.api.websocket import task_ws
from shared.config import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create AppContainer on startup, teardown on shutdown."""
    container = AppContainer(settings=Settings())
    await container.init()
    app.state.container = container
    yield
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

    # WebSocket
    app.websocket("/ws/tasks/{task_id}")(task_ws)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

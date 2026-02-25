"""Model status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from interface.api.schemas import ModelInfo, ModelStatusResponse

router = APIRouter(prefix="/api/models", tags=["models"])


def _container(request: Request):  # noqa: ANN202
    return request.app.state.container


@router.get("", response_model=list[str])
async def list_models(request: Request) -> list[str]:
    c = _container(request)
    return await c.llm.list_models()


@router.get("/status", response_model=ModelStatusResponse)
async def model_status(request: Request) -> ModelStatusResponse:
    c = _container(request)
    running = await c.ollama.is_running()
    model_names = await c.llm.list_models() if running else []
    models = [ModelInfo(name=m, available=True) for m in model_names]
    return ModelStatusResponse(
        ollama_running=running,
        default_model=c.settings.ollama_default_model,
        models=models,
    )

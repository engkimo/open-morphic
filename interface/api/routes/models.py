"""Model status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from interface.api.schemas import (
    ModelInfo,
    ModelStatusResponse,
    OllamaModelDetailResponse,
    OllamaPullRequest,
    OllamaSwitchRequest,
)

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


@router.get("/running")
async def running_models(request: Request) -> list[dict]:
    c = _container(request)
    return await c.ollama.get_running_models()


@router.post("/pull")
async def pull_model(body: OllamaPullRequest, request: Request) -> dict:
    c = _container(request)
    success = await c.manage_ollama.pull(body.name)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to pull {body.name}")
    return {"name": body.name, "success": True}


@router.delete("/{name}")
async def delete_model(name: str, request: Request) -> dict:
    c = _container(request)
    success = await c.manage_ollama.delete(name)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to delete {name}")
    return {"name": name, "deleted": True}


@router.post("/switch")
async def switch_model(body: OllamaSwitchRequest, request: Request) -> dict:
    c = _container(request)
    success = await c.manage_ollama.switch_default(body.name)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to switch to {body.name}")
    return {"name": body.name, "default": True}


@router.get("/{name}/info", response_model=OllamaModelDetailResponse)
async def model_info(name: str, request: Request) -> OllamaModelDetailResponse:
    c = _container(request)
    info = await c.manage_ollama.info(name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Model {name} not found")
    return OllamaModelDetailResponse(
        name=name,
        details=info,
    )

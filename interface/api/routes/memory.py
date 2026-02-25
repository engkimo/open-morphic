"""Memory search endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from interface.api.schemas import MemorySearchResponse

router = APIRouter(prefix="/api/memory", tags=["memory"])


def _container(request: Request):  # noqa: ANN202
    return request.app.state.container


@router.get("/search", response_model=MemorySearchResponse)
async def search_memory(q: str, request: Request) -> MemorySearchResponse:
    c = _container(request)
    result = await c.memory.retrieve(q, max_tokens=500)
    results = [line for line in result.split("\n") if line.strip()] if result else []
    return MemorySearchResponse(query=q, results=results, count=len(results))

"""Marketplace routes — search, install, list, uninstall tools."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from interface.api.schemas import (
    ToolCandidateResponse,
    ToolInstallRequest,
    ToolInstallResponse,
    ToolSearchResponse,
    ToolSuggestionResponse,
    ToolSuggestRequest,
)

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


def _container(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.container


@router.get("/search", response_model=ToolSearchResponse)
async def search_tools(
    q: str,
    request: Request,
    limit: int = 10,
) -> ToolSearchResponse:
    """Search the MCP Registry for tools."""
    c = _container(request)
    result = await c.install_tool.search(q, limit=limit)
    return ToolSearchResponse(
        query=result.query,
        candidates=[ToolCandidateResponse.from_candidate(c) for c in result.candidates],
        total_count=result.total_count,
        error=result.error,
    )


@router.post("/install", response_model=ToolInstallResponse)
async def install_tool(
    body: ToolInstallRequest,
    request: Request,
) -> ToolInstallResponse:
    """Install a tool by name (search + install best match)."""
    c = _container(request)
    result = await c.install_tool.install_by_name(body.name)
    if result.install_result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No tool found for '{body.name}'",
        )
    ir = result.install_result
    return ToolInstallResponse(
        tool_name=ir.tool_name,
        success=ir.success,
        message=ir.message,
        error=ir.error,
    )


@router.get("/installed", response_model=list[ToolCandidateResponse])
async def list_installed(request: Request) -> list[ToolCandidateResponse]:
    """List all installed tools."""
    c = _container(request)
    tools = c.install_tool.list_installed()
    return [ToolCandidateResponse.from_candidate(t) for t in tools]


@router.post("/suggest", response_model=ToolSuggestionResponse)
async def suggest_tools(
    body: ToolSuggestRequest,
    request: Request,
) -> ToolSuggestionResponse:
    """Suggest tools based on an error message."""
    c = _container(request)
    result = await c.discover_tools.suggest_for_failure(
        error_message=body.error_message,
        task_description=body.task_description,
    )
    return ToolSuggestionResponse(
        suggestions=[ToolCandidateResponse.from_candidate(s) for s in result.suggestions],
        queries_used=result.queries_used,
        count=len(result.suggestions),
    )


@router.delete("/{name}", response_model=ToolInstallResponse)
async def uninstall_tool(name: str, request: Request) -> ToolInstallResponse:
    """Uninstall a tool by name."""
    c = _container(request)
    result = await c.install_tool.uninstall(name)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.error or "Not found")
    return ToolInstallResponse(
        tool_name=result.tool_name,
        success=result.success,
        message=result.message,
    )

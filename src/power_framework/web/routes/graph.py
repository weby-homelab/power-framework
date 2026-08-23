"""Graph visualization and API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ..clients.power import PowerClient
from ..config import Settings, get_client, get_settings
from ..offload import run_power_call

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates

router = APIRouter()


@router.get("/graph", response_class=HTMLResponse)
async def graph_view(
    request: Request,
    max_nodes: int = Query(1000, ge=10, le=1000),
    focus_path: str | None = Query(None, max_length=512),
    max_depth: int = Query(2, ge=1, le=10),
    client: PowerClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Render interactive knowledge graph page with accessibility table fallback."""
    templates: Jinja2Templates = request.app.state.templates

    projection = await run_power_call(
        request,
        settings,
        client.get_graph_projection,
        max_nodes=max_nodes,
        focus_path=focus_path,
        max_depth=max_depth,
    )

    return templates.TemplateResponse(
        request=request,
        name="graph.html",
        context={
            "projection": projection,
            "max_nodes": max_nodes,
            "focus_path": focus_path,
            "max_depth": max_depth,
            "settings": settings,
        },
    )


@router.get("/api/graph/data", response_class=JSONResponse)
async def graph_data_api(
    request: Request,
    max_nodes: int = Query(1000, ge=10, le=1000),
    focus_path: str | None = Query(None, max_length=512),
    max_depth: int = Query(2, ge=1, le=10),
    client: PowerClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Return JSON formatted nodes and links for force-graph library."""
    projection = await run_power_call(
        request,
        settings,
        client.get_graph_projection,
        max_nodes=max_nodes,
        focus_path=focus_path,
        max_depth=max_depth,
    )
    return JSONResponse(
        content={
            "nodes": [n.model_dump() for n in projection.nodes],
            "links": [e.model_dump() for e in projection.edges],
            "total_nodes": projection.total_nodes,
            "total_edges": projection.total_edges,
            "is_truncated": projection.is_truncated,
            "source_revision": projection.source_revision,
            "actual_capability": projection.actual_capability,
            "degraded_reason": projection.degraded_reason,
            "max_depth": projection.max_depth,
            "ambiguities": projection.ambiguities,
        }
    )

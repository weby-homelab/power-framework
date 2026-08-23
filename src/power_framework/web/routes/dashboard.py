"""Dashboard route for the POWER Web UI."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..clients.power import PowerClient
from ..config import Settings, get_client, get_settings
from ..offload import run_power_call

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(
    request: Request,
    client: PowerClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Render main dashboard with vault metrics, active tasks, and system status."""
    templates: Jinja2Templates = request.app.state.templates

    stats, tasks, receipts, discovery = await asyncio.gather(
        run_power_call(request, settings, client.get_source_stats),
        run_power_call(request, settings, client.list_tasks, limit=10),
        run_power_call(request, settings, client.get_receipts, limit=5),
        run_power_call(request, settings, client.discover),
    )

    active_tasks = [t for t in tasks if t.state in {"ready", "working", "input-required"}]

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "stats": stats,
            "tasks": tasks,
            "active_tasks": active_tasks,
            "receipts": receipts,
            "discovery": discovery.data,
            "settings": settings,
        },
    )

"""Receipts and audit history route."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from ..clients.power import PowerClient
from ..config import Settings, get_client, get_settings
from ..offload import run_power_call

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/receipts")


@router.get("", response_class=HTMLResponse)
async def receipts_view(
    request: Request,
    limit: int = Query(100, ge=10, le=500),
    client: PowerClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Render content-free audit receipts history."""
    templates: Jinja2Templates = request.app.state.templates

    receipts = await run_power_call(request, settings, client.get_receipts, limit=limit)

    return templates.TemplateResponse(
        request=request,
        name="receipts.html",
        context={
            "receipts": receipts,
            "limit": limit,
            "settings": settings,
        },
    )

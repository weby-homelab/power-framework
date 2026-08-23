"""Decisions and human approval queue route."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..auth.csrf import validate_csrf
from ..clients.idempotency import key_for
from ..clients.power import PowerClient
from ..config import Settings, get_client, get_settings, require_mutation_enabled
from ..offload import run_power_call

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/decisions")


@router.get("", response_class=HTMLResponse)
async def decisions_view(
    request: Request,
    client: PowerClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Render approval and decision queue."""
    templates: Jinja2Templates = request.app.state.templates

    pending = await run_power_call(request, settings, client.list_decisions)

    return templates.TemplateResponse(
        request=request,
        name="decisions.html",
        context={
            "pending_decisions": pending,
            "settings": settings,
        },
    )


@router.post(
    "/{decision_id}/resolve",
    dependencies=[Depends(validate_csrf), Depends(require_mutation_enabled)],
)
async def resolve_decision_action(
    request: Request,
    decision_id: str,
    action: str = Form(...),  # approve / reject / provide_input
    input_value: str | None = Form(None),
    client: PowerClient = Depends(get_client),
) -> RedirectResponse:
    """Approve, reject, or provide input for a pending decision gate."""
    settings = get_settings(request)
    await run_power_call(
        request,
        settings,
        client.resolve_decision,
        decision_id,
        action=action,
        input_data={"value": input_value} if action == "provide_input" else None,
        idempotency_key=key_for("resolve", decision_id=decision_id, decision_action=action),
    )

    return RedirectResponse(url="/decisions", status_code=303)

"""Task Manager v2 cockpit routes and SSE event streaming."""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from ..auth.csrf import validate_csrf
from ..clients.idempotency import key_for
from ..clients.power import PowerClient
from ..config import Settings, get_client, get_settings, require_mutation_enabled
from ..errors import public_error_details, request_id_for
from ..offload import run_power_call

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi.templating import Jinja2Templates


router = APIRouter(prefix="/tasks")


@router.get("", response_class=HTMLResponse)
async def tasks_board_view(
    request: Request,
    state: str | None = Query(None, max_length=32),
    owner: str | None = Query(None, max_length=64),
    client: PowerClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Render Task Manager v2 board with status swimlanes."""
    templates: Jinja2Templates = request.app.state.templates

    tasks = await run_power_call(
        request,
        settings,
        client.list_tasks,
        state=state,
        owner=owner,
        limit=200,
    )

    # Group tasks by state for Kanban columns
    lanes = {
        "backlog": [t for t in tasks if t.state == "backlog"],
        "ready": [t for t in tasks if t.state in {"ready", "submitted"}],
        "working": [t for t in tasks if t.state == "working"],
        "blocked": [t for t in tasks if t.state in {"blocked", "input-required", "auth-required"}],
        "completed": [t for t in tasks if t.state == "completed"],
        "failed": [t for t in tasks if t.state in {"failed", "canceled", "rejected"}],
    }

    return templates.TemplateResponse(
        request=request,
        name="tasks.html",
        context={
            "tasks": tasks,
            "lanes": lanes,
            "filter_state": state,
            "filter_owner": owner,
            "settings": settings,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_task_view(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Render new task creation form."""
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="task_new.html",
        context={
            "settings": settings,
        },
    )


@router.post("/new", dependencies=[Depends(validate_csrf), Depends(require_mutation_enabled)])
async def create_task_action(
    request: Request,
    task_id: str = Form(..., max_length=128),
    title: str = Form(..., max_length=256),
    objective: str = Form("", max_length=4096),
    owner: str = Form("local", max_length=64),
    priority: str = Form("normal", max_length=16),
    authority: str = Form("read-only", max_length=16),
    client: PowerClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Create a new PowerTask v2."""
    await run_power_call(
        request,
        settings,
        client.create_task,
        task_id=task_id.strip(),
        title=title.strip(),
        objective=objective.strip(),
        owner=owner.strip(),
        priority=priority,
        authority=authority,
        idempotency_key=key_for(
            "create",
            task_id=task_id.strip(),
            title=title.strip(),
            objective=objective.strip(),
            owner=owner.strip(),
            priority=priority,
            authority=authority,
        ),
    )

    return RedirectResponse(url=f"/tasks/{task_id.strip()}", status_code=303)


@router.get("/{task_id}", response_class=HTMLResponse)
async def task_detail_view(
    request: Request,
    task_id: str,
    client: PowerClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Render task detail page with timeline, events journal, and actions."""
    templates: Jinja2Templates = request.app.state.templates

    task, events = await asyncio.gather(
        run_power_call(request, settings, client.get_task, task_id),
        run_power_call(request, settings, client.get_task_events, task_id),
    )

    return templates.TemplateResponse(
        request=request,
        name="task_detail.html",
        context={
            "task": task,
            "events": events,
            "settings": settings,
        },
    )


@router.post(
    "/{task_id}/transition",
    dependencies=[Depends(validate_csrf), Depends(require_mutation_enabled)],
)
async def transition_task_action(
    request: Request,
    task_id: str,
    new_state: str = Form(..., max_length=32),
    expected_revision: int = Form(...),
    next_action: str | None = Form(None, max_length=512),
    completion_postcondition: str | None = Form(None, max_length=4096),
    completion_artifact_refs: list[str] = Form([]),
    client: PowerClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Advance task state machine."""
    await run_power_call(
        request,
        settings,
        client.transition_task,
        task_id,
        new_state=new_state,
        expected_revision=expected_revision,
        next_action=next_action,
        completion_postcondition=completion_postcondition,
        completion_artifact_refs=completion_artifact_refs or None,
        idempotency_key=key_for(
            "transition",
            task_id=task_id,
            new_state=new_state,
            expected_revision=expected_revision,
            next_action=next_action,
        ),
    )

    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)


@router.get("/api/events/stream")
async def sse_task_events_stream(
    request: Request,
    task_id: str | None = Query(None, max_length=128),
    since_sequence: int = Query(0, ge=0),
    client: PowerClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Server-Sent Events stream for real-time task state and event updates."""

    limiter = getattr(request.app.state, "sse_connections", None)
    if limiter is None or not limiter.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Too many event streams")

    started_at = time.monotonic()

    async def event_generator() -> AsyncIterator[str]:
        last_seen_seq = since_sequence
        try:
            while time.monotonic() - started_at < settings.sse_max_lifetime_seconds:
                if await request.is_disconnected():
                    break
                remaining = settings.sse_max_lifetime_seconds - (time.monotonic() - started_at)
                if remaining <= 0:
                    break

                if task_id:
                    events = await run_power_call(
                        request,
                        settings,
                        client.get_task_events,
                        task_id,
                        since_sequence=last_seen_seq,
                        timeout_seconds=min(settings.power_call_timeout_seconds, remaining),
                    )
                    for ev in events:
                        last_seen_seq = max(last_seen_seq, ev.sequence)
                        yield f"event: task_event\ndata: {json.dumps(ev.model_dump())}\n\n"
                else:
                    tasks = await run_power_call(
                        request,
                        settings,
                        client.list_tasks,
                        limit=10,
                        timeout_seconds=min(settings.power_call_timeout_seconds, remaining),
                    )
                    summary = [
                        {"id": t.task_id, "state": t.state, "revision": t.revision} for t in tasks
                    ]
                    yield f"event: tasks_summary\ndata: {json.dumps(summary)}\n\n"

                yield ": heartbeat\n\n"
                await asyncio.sleep(min(2, max(0, remaining)))
        except Exception as exc:
            code, message = public_error_details(exc)
            error_payload = {
                "code": code,
                "message": message,
                "request_id": request_id_for(request),
            }
            yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
        finally:
            limiter.release()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

"""Search route for multi-modal knowledge retrieval."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from ..clients.power import PowerClient
from ..config import Settings, get_client, get_settings
from ..offload import run_power_call

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/search")


def _normalize_search_results(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize raw search envelope results for consistent template consumption."""
    raw_items = data.get("results") or data.get("items") or []
    normalized_items: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, dict):
            source_value = item.get("source")
            source: dict[str, Any] = source_value if isinstance(source_value, dict) else {}
            metadata_value = item.get("metadata")
            metadata: dict[str, Any] = metadata_value if isinstance(metadata_value, dict) else {}

            path = source.get("path") or item.get("path") or item.get("rel_path") or ""
            title = (
                metadata.get("title") or item.get("title") or (Path(path).stem if path else "Note")
            )
            description = metadata.get("description") or item.get("description") or ""
            note_type = metadata.get("note_type") or item.get("note_type") or ""
            tags = metadata.get("tags") or item.get("tags") or []
            snippet = item.get("snippet") or item.get("matched_text") or description
            score = item.get("score", 0.0)

            normalized_items.append(
                {
                    "path": path,
                    "rel_path": path,
                    "title": title,
                    "description": description,
                    "note_type": note_type,
                    "tags": tags,
                    "snippet": snippet,
                    "score": score,
                    "source": source,
                    "metadata": metadata,
                }
            )
    return {
        **data,
        "results": normalized_items,
        "items": normalized_items,
    }


@router.get("", response_class=HTMLResponse)
async def search_view(
    request: Request,
    q: str = Query("", max_length=512, description="Search query"),
    mode: str = Query(
        "auto", max_length=16, description="Retrieval mode: auto, fts, semantic, reranked"
    ),
    limit: int = Query(20, ge=1, le=100),
    client: PowerClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Execute search query and display results with provenance."""
    templates: Jinja2Templates = request.app.state.templates

    results_data: dict[str, Any] = {}
    if q.strip():
        env = await run_power_call(
            request,
            settings,
            client.search,
            q,
            mode=mode,
            max_results=limit,
        )
        results_data = _normalize_search_results(env.data)

    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "query": q,
            "mode": mode,
            "results": results_data,
            "settings": settings,
        },
    )

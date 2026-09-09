"""Read-only fleet probe status and experimental/custom-discovery metadata route."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ..clients.power import PowerClient
from ..config import Settings, get_client, get_settings
from ..offload import run_power_call

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_FLEET_TOPOLOGY: list[dict[str, Any]] = [
    {
        "node_id": "local-core",
        "role": "Authoritative Core",
        "host": "127.0.0.1",
        "port": 8080,
        "endpoint": "local",
        "authority": "authoritative",
        "vault_id_type": "primary",
    },
    {
        "node_id": "remote-ws",
        "role": "AI Workstation",
        "host": "127.0.0.1",
        "port": 8080,
        "endpoint": "remote-ws:8080",
        "authority": "agent-executor",
        "vault_id_type": "compute-node",
    },
    {
        "node_id": "docker-plane",
        "role": "Application Plane",
        "host": "127.0.0.1",
        "port": 8080,
        "endpoint": "docker-plane:8080",
        "authority": "operator-cockpit",
        "vault_id_type": "mounted",
    },
]
_MAX_FEDERATION_NODES = 16


def _get_fleet_topology(settings: Settings) -> list[dict[str, Any]]:
    """Load configurable federation topology from settings or fallback to default."""
    if settings.federation_nodes:
        try:
            parsed = json.loads(settings.federation_nodes)
            if not isinstance(parsed, list) or len(parsed) > _MAX_FEDERATION_NODES:
                raise ValueError("federation topology exceeds its node limit")
            validated: list[dict[str, Any]] = []
            for item in parsed:
                if not isinstance(item, dict):
                    raise ValueError("federation topology entries must be objects")
                host = item.get("host", "127.0.0.1")
                port = item.get("port", 8080)
                if (
                    not isinstance(host, str)
                    or not host.strip()
                    or len(host) > 253
                    or any(char.isspace() for char in host)
                    or "://" in host
                    or not isinstance(port, int)
                    or isinstance(port, bool)
                    or not 1 <= port <= 65535
                ):
                    raise ValueError("federation topology contains an invalid host or port")
                validated.append({**item, "host": host, "port": port})
            return validated
        except Exception as exc:
            logger.warning(
                "Ignoring invalid POWER_WEB_FEDERATION_NODES configuration exception_type=%s",
                type(exc).__name__,
            )
    return DEFAULT_FLEET_TOPOLOGY


async def _probe_node(node: dict[str, Any], vault_id: str, total_notes: int) -> dict[str, Any]:
    """Asynchronously probe TCP port with low timeout and measure latency."""
    host = str(node.get("host", "127.0.0.1"))
    raw_port = node.get("port", 8080)
    port = raw_port if isinstance(raw_port, int) and not isinstance(raw_port, bool) else 8080
    t0 = time.perf_counter()
    status = "unreachable"
    latency_ms: float | None = None

    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=0.8)
        writer.close()
        await writer.wait_closed()
        status = "online"
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    except Exception:
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)

    vault_id_type = str(node.get("vault_id_type", "primary"))
    node_vault_id = vault_id if vault_id_type in {"primary", "mounted"} else vault_id_type
    notes_count = total_notes if vault_id_type in {"primary", "mounted"} else "-"

    return {
        "node_id": node.get("node_id", "node"),
        "role": node.get("role", "Node"),
        "endpoint": node.get("endpoint", f"{host}:{port}"),
        "status": status,
        "latency_ms": latency_ms,
        "vault_id": node_vault_id,
        "notes_count": notes_count,
        "trust_level": node.get("authority", "read-only-federated"),
    }


@router.get("/federation", response_class=HTMLResponse)
async def federation_view(
    request: Request,
    client: PowerClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Render federated nodes status and multi-vault search cockpit with live probe."""
    templates: Jinja2Templates = request.app.state.templates

    discovery, stats = await asyncio.gather(
        run_power_call(request, settings, client.discover),
        run_power_call(request, settings, client.get_source_stats),
    )
    topology = _get_fleet_topology(settings)

    # Parallel probing remains bounded both by node count and active probes.
    probe_limiter = asyncio.Semaphore(
        min(_MAX_FEDERATION_NODES, settings.power_call_max_concurrency)
    )

    async def bounded_probe(node: dict[str, Any]) -> dict[str, Any]:
        async with probe_limiter:
            return await _probe_node(node, vault_id=stats.vault_id, total_notes=stats.total_notes)

    nodes = await asyncio.wait_for(
        asyncio.gather(*(bounded_probe(node) for node in topology)),
        timeout=settings.power_call_timeout_seconds,
    )

    return templates.TemplateResponse(
        request=request,
        name="federation.html",
        context={
            "nodes": nodes,
            "discovery": discovery.data,
            "stats": stats,
            "settings": settings,
        },
    )


@router.get("/federation/agent.json", response_class=JSONResponse)
@router.get("/.well-known/agent.json", response_class=JSONResponse)
async def a2a_agent_card(
    request: Request,
    client: PowerClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Expose experimental custom discovery metadata, not A2A conformance."""
    stats, discovery = await asyncio.gather(
        run_power_call(request, settings, client.get_source_stats),
        run_power_call(request, settings, client.discover),
    )
    from power_framework.core.utils import __version__ as power_version

    card = {
        "schema_version": "custom-discovery.v1",
        "protocol": "experimental/custom-discovery",
        "name": "Second Brain Cockpit",
        "node_id": "local-core",
        "vault_id": stats.vault_id,
        "authority": "authoritative",
        "framework": {
            "name": "P.O.W.E.R",
            "version": power_version,
        },
        "capabilities": [
            "power.search",
            "power.source.read",
            "power.source.list",
            "power.source.stats",
            "power.task.status",
            "power.graph",
        ],
        "discovery": discovery.data,
        "security": {
            "auth_required": settings.auth_enabled,
            "encryption": "TLS / Encrypted Transport",
            "fail_closed": True,
            "read_only": True,
        },
    }
    return JSONResponse(content=card)

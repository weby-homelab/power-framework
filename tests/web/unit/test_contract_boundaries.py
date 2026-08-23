"""Focused tests for the public Web UI contract boundaries."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from threading import Lock

import anyio
import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request as StarletteRequest

from power_framework.web.app import create_app
from power_framework.web.config import Settings
from power_framework.web.errors import (
    PowerCallTimeoutError,
    http_exception_handler,
    public_error_details,
    request_validation_handler,
    unhandled_exception_handler,
)
from power_framework.web.offload import run_power_call


def _request(path: str = "/") -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 1),
        "server": ("testserver", 80),
        "root_path": "",
    }
    return StarletteRequest(scope)


def test_public_exception_mapping_never_reflects_secret_details() -> None:
    secret = "/brain/private-note.md?token=do-not-leak"
    assert public_error_details(FileNotFoundError(secret)) == (
        "not_found",
        "The requested resource was not found.",
    )
    assert public_error_details(PermissionError(secret)) == (
        "permission_denied",
        "You do not have permission to perform this operation.",
    )
    from power_framework.core.errors import ConflictError

    assert public_error_details(ConflictError(f"conflict at {secret}"))[0] == "conflict"
    assert public_error_details(ValueError(f"conflict at {secret}"))[0] == "invalid_request"
    assert secret not in " ".join(public_error_details(RuntimeError(secret)))


@pytest.mark.asyncio
async def test_offload_uses_bounded_limiter_and_timeout() -> None:
    app = FastAPI()
    app.state.power_call_limiter = anyio.CapacityLimiter(1)
    request = _request()
    request.scope["app"] = app
    settings = Settings(auth_enabled=False, power_call_timeout_seconds=0.1)

    with pytest.raises(PowerCallTimeoutError):
        await run_power_call(request, settings, time.sleep, 0.2)


@pytest.mark.asyncio
async def test_offload_never_exceeds_shared_worker_bound() -> None:
    app = FastAPI()
    app.state.power_call_limiter = anyio.CapacityLimiter(1)
    request = _request()
    request.scope["app"] = app
    settings = Settings(auth_enabled=False, power_call_timeout_seconds=1.0)
    lock = Lock()
    active = 0
    peak = 0

    def blocking_probe() -> None:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with lock:
            active -= 1

    await asyncio.gather(
        run_power_call(request, settings, blocking_probe),
        run_power_call(request, settings, blocking_probe),
    )
    assert peak == 1


def test_unified_plan_is_machine_readable() -> None:
    root = Path(__file__).parents[3]
    plan_path = root / "release" / "unified-release-plan.json"
    assert plan_path.is_file()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["schema"] == "power.unified.plan.v1"
    assert plan["target_version"] == "3.7.6"
    assert plan["canonical_repository"] == "weby-homelab/power-framework"
    assert plan["canonical_package"] == "power-framework"
    assert plan["invariants"]["single_repo"] is True
    assert plan["invariants"]["single_package"] is True
    assert plan["invariants"]["docker_web_only"] is True


def test_route_inventory_offloads_power_calls() -> None:
    root = Path(__file__).parents[3] / "src" / "power_framework" / "web" / "routes"
    notes = (root / "notes.py").read_text(encoding="utf-8")
    assert "client.list_sources" in notes
    assert "client.get_source_stats" in notes
    for route_file in root.glob("*.py"):
        source = route_file.read_text(encoding="utf-8")
        if "PowerClient" in source:
            assert "run_power_call" in source, route_file.name


def test_web_application_service_boundary_has_no_direct_backend_bypass() -> None:
    root = Path(__file__).parents[3] / "src" / "power_framework" / "web"
    client_source = (root / "clients" / "power.py").read_text(encoding="utf-8")
    assert "ApplicationService" in client_source
    assert "self._service = ApplicationService" in client_source

    web_sources = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    assert "subprocess" not in web_sources
    assert "POWER_MCP_TRANSPORT" not in web_sources


def test_async_routes_have_public_error_handler() -> None:
    app = create_app(Settings(auth_enabled=False))
    assert app.exception_handlers[RequestValidationError] is request_validation_handler
    assert app.exception_handlers[Exception] is unhandled_exception_handler


def test_sse_limits_are_configured_and_connection_semaphore_is_bounded() -> None:
    app = create_app(
        Settings(
            auth_enabled=False,
            sse_max_connections=2,
            sse_max_lifetime_seconds=60,
        )
    )
    assert isinstance(app.state.sse_connections, threading.BoundedSemaphore)
    assert app.state.settings.sse_max_lifetime_seconds == 60
    assert app.state.settings.sse_max_connections == 2


def test_sse_source_contract_has_disconnect_sleep_and_bounded_power_polling() -> None:
    source = (
        Path(__file__).parents[3] / "src" / "power_framework" / "web" / "routes" / "tasks.py"
    ).read_text(encoding="utf-8")
    assert "await request.is_disconnected()" in source
    assert "settings.sse_max_lifetime_seconds" in source
    assert "await asyncio.sleep" in source
    assert "timeout_seconds=min(settings.power_call_timeout_seconds, remaining)" in source
    assert "public_error_details" in source
    assert "since_sequence: int = Query(0, ge=0)" in source


@pytest.mark.asyncio
async def test_http_exception_handler_redacts_route_detail() -> None:
    request = _request()
    request.state.request_id = "corr-123"
    response = await http_exception_handler(
        request,
        StarletteHTTPException(status_code=404, detail="/brain/secret.md?token=hidden"),
    )
    body = bytes(response.body)
    assert response.status_code == 404
    assert b"secret.md" not in body
    assert b"token=hidden" not in body
    assert b"corr-123" in body

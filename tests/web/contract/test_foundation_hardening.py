"""Web F1/F2/F5 contracts for the foundation hardening gate."""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from typing import TYPE_CHECKING

import anyio
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from power_framework.core.principal import Principal
from power_framework.web.app import create_app
from power_framework.web.clients.power import PowerClient
from power_framework.web.config import Settings
from power_framework.web.errors import (
    PowerCallCompletedAfterCancellationError,
    PowerCallCompletedAfterDeadlineError,
)
from power_framework.web.offload import run_power_call

if TYPE_CHECKING:
    from pathlib import Path


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match
    return match.group(1)


def _proposal_id(html: str) -> str:
    match = re.search(r'name="proposal_id"\s+value="([0-9a-f]{64})"', html)
    assert match
    return match.group(1)


@pytest.fixture
def web_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "web-foundation-vault"
    vault.mkdir()
    (vault / ".power").mkdir()
    (vault / "01_Projects").mkdir()
    (vault / "01_Projects" / "Note.md").write_text(
        "---\ntype: Project\ntitle: Note\ndescription: Baseline\n"
        "timestamp: 2026-09-09T00:00:00Z\n---\n\nBaseline\n",
        encoding="utf-8",
    )
    return vault


def _web_client(vault: Path, *, host: str = "127.0.0.1") -> TestClient:
    settings = Settings(
        vault_path=vault,
        host=host,
        auth_enabled=False,
        cookie_secure=False,
    )
    return TestClient(create_app(settings))


def test_web_apply_omitted_false_and_malformed_approval_fail_closed(
    web_vault: Path,
) -> None:
    """An omitted or non-exact approval value cannot reach the apply client."""
    client = _web_client(web_vault)
    edit = client.get("/notes/edit?path=01_Projects/Note.md")
    proposal = client.post(
        "/notes/propose",
        data={
            "csrf_token": _csrf(edit.text),
            "path": "01_Projects/Note.md",
            "content": (
                "---\ntype: Project\ntitle: Changed\ndescription: Updated\n"
                "timestamp: 2026-09-09T00:00:00Z\n---\n\nChanged\n"
            ),
        },
    )
    assert proposal.status_code == 200
    proposal_id = _proposal_id(proposal.text)
    csrf = _csrf(proposal.text)

    omitted = client.post(
        "/notes/apply",
        data={"csrf_token": csrf, "proposal_id": proposal_id},
        follow_redirects=False,
    )
    assert omitted.status_code == 422

    for value in ("false", "yes", "1"):
        rejected = client.post(
            "/notes/apply",
            data={"csrf_token": csrf, "proposal_id": proposal_id, "approved": value},
            follow_redirects=False,
        )
        assert rejected.status_code == 403, value

    assert "Baseline" in (web_vault / "01_Projects" / "Note.md").read_text(encoding="utf-8")


def test_web_session_subject_and_request_id_reach_application_receipt(web_vault: Path) -> None:
    """The verified web binding is carried without conflating it with actor text."""
    client = PowerClient(
        web_vault,
        principal=Principal.web_signed_session("admin"),
        request_id="web-request-1",
    )

    envelope = client.discover(actor="forged-attribution")

    assert envelope.receipt.request_id == "web-request-1"
    assert envelope.receipt.principal_binding == "WEB_SIGNED_SESSION"
    assert envelope.receipt.principal_ref is not None
    assert envelope.receipt.principal_ref != "admin"


def test_real_signed_web_session_populates_server_derived_principal(web_vault: Path) -> None:
    """The middleware binds the verified session subject, not a request field."""
    settings = Settings(
        vault_path=web_vault,
        auth_enabled=True,
        admin_password="test-password",
        cookie_secure=False,
        session_max_age_seconds=300,
    )
    app = create_app(settings)

    @app.get("/_foundation-principal")
    async def foundation_principal(request: Request):
        principal = request.state.principal
        return {
            "binding": principal.binding if principal is not None else None,
            "ref": principal.ref if principal is not None else None,
            "subject": request.state.session_subject,
        }

    client = TestClient(app)
    login = client.get("/login")
    response = client.post(
        "/login",
        data={"password": "test-password", "csrf_token": _csrf(login.text)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    session = response.cookies.get("power_web_session")
    assert session is not None
    client.cookies.set("power_web_session", session)

    principal = client.get("/_foundation-principal").json()

    assert principal["binding"] == "WEB_SIGNED_SESSION"
    assert principal["subject"] == "admin"
    assert principal["ref"] != "admin"


def test_auth_disabled_non_loopback_bind_fails_closed(web_vault: Path) -> None:
    """Disabling login is not a remote anonymous mutation mode."""
    remote_bind = ".".join(("0", "0", "0", "0"))
    client = _web_client(web_vault, host=remote_bind)

    private = client.get("/dashboard")
    readiness = client.get("/readiness")

    assert private.status_code == 403
    assert readiness.status_code == 503
    assert any("loopback" in issue for issue in readiness.json()["issues"])


def test_federation_config_rejects_unbounded_or_url_like_nodes(web_vault: Path) -> None:
    """Configured discovery probes have bounded, host/port-only input."""
    from power_framework.web.routes.federation import DEFAULT_FLEET_TOPOLOGY, _get_fleet_topology

    too_many = [{"host": "127.0.0.1", "port": 8080}] * 17
    settings = Settings(
        vault_path=web_vault,
        auth_enabled=False,
        federation_nodes=json.dumps(too_many),
    )
    assert _get_fleet_topology(settings) == DEFAULT_FLEET_TOPOLOGY

    settings.federation_nodes = json.dumps([{"host": "http://127.0.0.1", "port": 8080}])
    assert _get_fleet_topology(settings) == DEFAULT_FLEET_TOPOLOGY


@pytest.mark.asyncio
async def test_mutation_offload_joins_worker_and_reports_late_completion() -> None:
    """A timed-out mutation worker is joined before the caller gets an error."""
    app = FastAPI()
    app.state.power_call_limiter = anyio.CapacityLimiter(1)
    request = type("RequestStub", (), {})()
    request.app = app
    request.state = type("State", (), {"request_id": "offload-request-1"})()
    settings = Settings(auth_enabled=False, power_call_timeout_seconds=0.1)
    finished = threading.Event()

    def slow_mutation() -> str:
        time.sleep(0.15)
        finished.set()
        return "committed"

    with pytest.raises(PowerCallCompletedAfterDeadlineError):
        await run_power_call(
            request,
            settings,
            slow_mutation,
            mutation=True,
        )

    assert finished.is_set()


@pytest.mark.asyncio
async def test_canceled_mutation_offload_reports_joined_outcome() -> None:
    """Cancellation cannot detach an in-flight mutation from its caller."""
    app = FastAPI()
    app.state.power_call_limiter = anyio.CapacityLimiter(1)
    request = type("RequestStub", (), {})()
    request.app = app
    request.state = type("State", (), {"request_id": "cancel-request-1"})()
    settings = Settings(auth_enabled=False, power_call_timeout_seconds=1.0)
    finished = threading.Event()

    def slow_mutation() -> str:
        time.sleep(0.04)
        finished.set()
        return "committed"

    running = asyncio.create_task(run_power_call(request, settings, slow_mutation, mutation=True))
    await asyncio.sleep(0.005)
    running.cancel()

    with pytest.raises(PowerCallCompletedAfterCancellationError):
        await running
    assert finished.is_set()

"""Contract tests for security hardening, CSRF defense, rate limiting, and fail-closed auth."""

from __future__ import annotations

import re
import threading
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from power_framework.web.app import create_app
from power_framework.web.auth.password import hash_password
from power_framework.web.auth.rate_limiter import global_login_rate_limiter
from power_framework.web.config import Settings

if TYPE_CHECKING:
    from pathlib import Path


def _extract_csrf(response) -> str:
    """Helper to extract csrf_token from HTML response."""
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text)
    return match.group(1) if match else ""


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> None:
    """Reset rate limiter state before each test."""
    global_login_rate_limiter.reset_all()


@pytest.fixture
def test_vault(tmp_path: Path) -> Path:
    """Create test vault."""
    vault = tmp_path / "sec_vault"
    vault.mkdir()
    (vault / ".power").mkdir()
    (vault / "01_Projects").mkdir()
    (vault / "01_Projects" / "TestDoc.md").write_text(
        "---\ntype: Project\ntitle: TestDoc\ntags: [test]\ntimestamp: 2026-08-14T12:00:00+00:00\n---\n# Test",
        encoding="utf-8",
    )
    return vault


def test_healthz_unauthenticated_probe(test_vault: Path) -> None:
    """Ensure /healthz is accessible without credentials even when auth is strictly enabled."""
    settings = Settings(
        vault_path=test_vault, auth_enabled=True, admin_password="t_pw", cookie_secure=False
    )
    app = create_app(settings)
    client = TestClient(app)

    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_fail_closed_on_unconfigured_auth(test_vault: Path) -> None:
    """Ensure login attempts fail closed with HTTP 500 when auth is enabled without credentials."""
    settings = Settings(
        vault_path=test_vault,
        auth_enabled=True,
        admin_password="",
        admin_password_hash=None,
        cookie_secure=False,
    )
    app = create_app(settings)
    client = TestClient(app)

    # 1. Login view renders
    resp_login = client.get("/login")
    assert resp_login.status_code == 200
    csrf = _extract_csrf(resp_login)

    # 2. Login action fails closed
    resp_action = client.post(
        "/login",
        data={"password": "any_pw", "csrf_token": csrf},
    )
    assert resp_action.status_code == 500
    assert "fail-closed" in resp_action.text.lower() or "unconfigured" in resp_action.text.lower()


def test_login_rate_limiting_and_lockout(test_vault: Path) -> None:
    """Ensure multiple failed login attempts trigger HTTP 429 lockout."""
    settings = Settings(
        vault_path=test_vault, auth_enabled=True, admin_password="good_pw", cookie_secure=False
    )
    app = create_app(settings)
    client = TestClient(app)

    # Get CSRF token
    resp_login = client.get("/login")
    csrf = _extract_csrf(resp_login)

    # 4 failed attempts should return 401
    for _ in range(4):
        resp = client.post("/login", data={"password": "bad_pw", "csrf_token": csrf})
        assert resp.status_code == 401

    # 5th failed attempt should trigger lockout (429)
    resp_5th = client.post("/login", data={"password": "bad_pw", "csrf_token": csrf})
    assert resp_5th.status_code == 429
    assert "locked" in resp_5th.text.lower() or "wait" in resp_5th.text.lower()

    # Subsequent attempt even with correct password is still locked out
    resp_locked = client.post("/login", data={"password": "good_pw", "csrf_token": csrf})
    assert resp_locked.status_code == 429


def test_hashed_password_authentication(test_vault: Path) -> None:
    """Test successful login using PBKDF2 hashed administrator password."""
    pwd_hash = hash_password("h_key", iterations=10_000)
    settings = Settings(
        vault_path=test_vault,
        auth_enabled=True,
        admin_password="",
        admin_password_hash=pwd_hash,
        cookie_secure=False,
    )
    app = create_app(settings)
    client = TestClient(app)

    # Get CSRF token
    resp_login = client.get("/login")
    csrf = _extract_csrf(resp_login)

    # Wrong password -> 401
    resp_bad = client.post("/login", data={"password": "bad_pw", "csrf_token": csrf})
    assert resp_bad.status_code == 401

    # Correct password -> 303 redirect with session cookie
    resp_good = client.post(
        "/login",
        data={"password": "h_key", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert resp_good.status_code == 303
    assert resp_good.headers["location"] == "/dashboard"
    assert resp_good.cookies.get("power_web_session") is not None


def test_csrf_rejection_on_missing_or_tampered_token(test_vault: Path) -> None:
    """Ensure state-changing POST routes strictly reject missing or forged CSRF tokens."""
    settings = Settings(vault_path=test_vault, auth_enabled=False, cookie_secure=False)
    app = create_app(settings)
    client = TestClient(app)

    # 1. Missing CSRF on notes propose
    resp_no_csrf = client.post(
        "/notes/propose",
        data={"path": "01_Projects/TestDoc.md", "content": "# Updated"},
    )
    assert resp_no_csrf.status_code == 403

    # 2. Tampered CSRF on notes propose
    resp_edit = client.get("/notes/edit?path=01_Projects/TestDoc.md")
    csrf = _extract_csrf(resp_edit)
    resp_bad_csrf = client.post(
        "/notes/propose",
        data={
            "path": "01_Projects/TestDoc.md",
            "content": "# Updated",
            "csrf_token": csrf + "forged",
        },
    )
    assert resp_bad_csrf.status_code == 403

    # 3. Missing CSRF on task creation
    resp_task_no_csrf = client.post(
        "/tasks/new",
        data={"task_id": "t1", "title": "Title"},
    )
    assert resp_task_no_csrf.status_code == 403


def test_csp_header_security(test_vault: Path) -> None:
    """Ensure Content-Security-Policy headers do not contain unsafe-inline for scripts."""
    settings = Settings(vault_path=test_vault, auth_enabled=False, cookie_secure=False)
    app = create_app(settings)
    client = TestClient(app)

    resp = client.get("/dashboard")
    csp = resp.headers.get("Content-Security-Policy", "")
    assert csp != ""
    assert "script-src 'self'" in csp
    assert "script-src 'self' 'unsafe-inline'" not in csp
    assert "frame-ancestors 'self'" in csp
    assert "form-action 'self'" in csp
    assert resp.headers["Strict-Transport-Security"].startswith("max-age=")
    assert resp.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    assert resp.headers["Cache-Control"] == "no-store"
    assert '/static/js/app.js" defer' in resp.text
    assert "<script>" not in resp.text


def test_secure_cookie_defaults_and_https_login(test_vault: Path) -> None:
    """Ensure production defaults protect cookies and expose transport headers."""
    default_settings = Settings(vault_path=test_vault)
    assert default_settings.cookie_secure is True
    assert default_settings.session_max_age_seconds == 86400

    settings = Settings(
        vault_path=test_vault,
        auth_enabled=True,
        admin_password="good_pw",
        cookie_secure=True,
    )
    app = create_app(settings)
    client = TestClient(app, base_url="https://testserver")
    login_page = client.get("/login")
    csrf = _extract_csrf(login_page)
    response = client.post(
        "/login",
        data={"password": "good_pw", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Secure" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert response.headers["Strict-Transport-Security"].startswith("max-age=")


def test_logout_requires_csrf_token(test_vault: Path) -> None:
    """Ensure logout cannot be triggered by a cross-site form without a token."""
    settings = Settings(vault_path=test_vault, auth_enabled=False, cookie_secure=False)
    app = create_app(settings)
    client = TestClient(app)
    dashboard = client.get("/dashboard")
    csrf = _extract_csrf(dashboard)

    assert client.post("/logout").status_code == 403
    assert (
        client.post("/logout", data={"csrf_token": csrf}, follow_redirects=False).status_code == 303
    )


def test_request_body_and_sse_limits(test_vault: Path) -> None:
    """Ensure oversized requests and excess event streams fail before expensive work."""
    settings = Settings(
        vault_path=test_vault,
        auth_enabled=False,
        cookie_secure=False,
        max_upload_bytes=1024,
        sse_max_connections=1,
    )
    app = create_app(settings)
    client = TestClient(app)

    oversized = client.post(
        "/notes/propose",
        content=b"x" * 1025,
        headers={"content-type": "application/octet-stream"},
    )
    assert oversized.status_code == 413

    app.state.sse_connections = threading.BoundedSemaphore(0)
    stream = client.get("/tasks/api/events/stream")
    assert stream.status_code == 429

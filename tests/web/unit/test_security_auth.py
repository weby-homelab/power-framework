"""Unit tests for password hashing, fail-closed verifier, and rate limiting."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from power_framework.web.auth.csrf import validate_csrf
from power_framework.web.auth.password import hash_password, is_auth_configured, verify_password
from power_framework.web.auth.rate_limiter import LoginRateLimiter
from power_framework.web.config import Settings


def test_password_fail_closed_unconfigured() -> None:
    """Ensure authentication fails closed when no password or hash is configured."""
    settings = Settings(auth_enabled=True, admin_password="", admin_password_hash=None)
    assert is_auth_configured(settings) is False

    # Attempting to verify any password against unconfigured settings must return False
    assert verify_password("any-password", admin_password="", admin_password_hash=None) is False
    assert verify_password("", admin_password="", admin_password_hash=None) is False


def test_password_plaintext_verification() -> None:
    """Verify plaintext password matching using constant-time comparison."""
    assert verify_password("test_pass", admin_password="test_pass") is True
    assert verify_password("wrong", admin_password="test_pass") is False
    assert verify_password("", admin_password="test_pass") is False


def _request_for_app(app: FastAPI) -> Request:
    """Build a minimal request scope for CSRF dependency tests."""
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/mutate",
            "raw_path": b"/mutate",
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
            "root_path": "",
            "app": app,
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "settings",
    [
        None,
        SimpleNamespace(),
        SimpleNamespace(secret_key=123, session_cookie_name="session", csrf_cookie_name="csrf"),
        SimpleNamespace(secret_key="secret", session_cookie_name="", csrf_cookie_name="csrf"),
        SimpleNamespace(secret_key="secret", session_cookie_name="session", csrf_cookie_name=None),
    ],
)
async def test_csrf_fails_closed_for_missing_or_malformed_settings(settings: object) -> None:
    """Reject missing, wrong-typed, or empty application CSRF settings."""
    app = FastAPI()
    if settings is not None:
        app.state.settings = settings

    with pytest.raises(RuntimeError, match="CSRF settings are missing or malformed"):
        await validate_csrf(_request_for_app(app))


def test_password_pbkdf2_hash_and_verification() -> None:
    """Test PBKDF2-HMAC-SHA256 password hashing and verification."""
    raw_pwd = "pass_pbkdf"
    pwd_hash = hash_password(raw_pwd, iterations=10_000)

    assert pwd_hash.startswith("pbkdf2:sha256:10000$")
    assert verify_password(raw_pwd, admin_password_hash=pwd_hash) is True
    assert verify_password("WrongPassword", admin_password_hash=pwd_hash) is False
    assert verify_password("", admin_password_hash=pwd_hash) is False


def test_rate_limiter_lockout_lifecycle() -> None:
    """Test rate limiter attempt counting, lockout triggering, and reset."""
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=60, base_lockout_seconds=10)
    key = "192.168.1.50"

    # Initially not locked
    locked, remaining = limiter.is_locked(key)
    assert locked is False
    assert remaining == 0

    # Failure 1
    count, is_locked, dur = limiter.record_failure(key)
    assert count == 1
    assert is_locked is False

    # Failure 2
    count, is_locked, dur = limiter.record_failure(key)
    assert count == 2
    assert is_locked is False

    # Failure 3 -> triggers lockout
    count, is_locked, dur = limiter.record_failure(key)
    assert count == 3
    assert is_locked is True
    assert dur >= 10

    # Check is_locked status
    locked, remaining = limiter.is_locked(key)
    assert locked is True
    assert remaining > 0

    # Success resets lockout
    limiter.record_success(key)
    locked, remaining = limiter.is_locked(key)
    assert locked is False
    assert remaining == 0

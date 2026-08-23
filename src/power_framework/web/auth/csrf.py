"""CSRF protection tokens and middleware helpers."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from typing import Protocol

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


class CsrfSettings(Protocol):
    """Settings shape required by CSRF helpers without importing Web config."""

    secret_key: str
    session_cookie_name: str
    csrf_cookie_name: str


def generate_csrf_token(secret_key: str, session_id: str) -> str:
    """Generate deterministic HMAC-SHA256 CSRF token for a given session or cookie ID."""
    key = secret_key.encode("utf-8")
    msg = f"csrf:{session_id}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def verify_csrf_token(secret_key: str, session_id: str, token: str) -> bool:
    """Constant-time comparison of submitted CSRF token."""
    if not token or not session_id or not secret_key:
        return False
    expected = generate_csrf_token(secret_key, session_id)
    return hmac.compare_digest(expected, token)


def get_csrf_token(request: Request, settings: CsrfSettings) -> str:
    """
    Get or derive the valid CSRF token for the current request.

    Binds to active session cookie if authenticated, or falls back to
    ephemeral CSRF cookie / state token.
    """
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        session_id = request.cookies.get(settings.csrf_cookie_name)

    if not session_id:
        # Check if already generated during this request processing
        session_id = getattr(request.state, "csrf_cookie_val", None)
        if not session_id:
            session_id = secrets.token_hex(16)
            request.state.csrf_cookie_val = session_id

    return generate_csrf_token(settings.secret_key, session_id)


async def validate_csrf(request: Request) -> None:
    """
    FastAPI dependency to enforce CSRF token validity on state-changing requests.

    Extracts token from form body (`csrf_token`) or HTTP headers (`X-CSRF-Token`).
    Raises 403 Forbidden on mismatch or missing token.
    """
    from ..config import Settings, get_global_settings

    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        settings = get_global_settings()

    # Try header first (for API / fetch requests)
    header_csrf = request.headers.get("X-CSRF-Token") or request.headers.get("X-XSRF-Token")
    form_csrf: str | None = None

    # If not in header and content type is form, parse form body
    if not header_csrf:
        content_type = request.headers.get("content-type", "")
        if (
            "application/x-www-form-urlencoded" in content_type
            or "multipart/form-data" in content_type
        ):
            try:
                form = await request.form()
                form_csrf = form.get("csrf_token")  # type: ignore[assignment]
            except Exception as exc:
                logger.warning("Failed to parse form for CSRF token: %s", exc)

    extracted_csrf = header_csrf or form_csrf
    session_id = request.cookies.get(settings.session_cookie_name) or request.cookies.get(
        settings.csrf_cookie_name
    )

    if (
        not extracted_csrf
        or not session_id
        or not verify_csrf_token(settings.secret_key, session_id, str(extracted_csrf))
    ):
        logger.warning(
            "CSRF validation failed for path=%s method=%s (has_token=%s, has_cookie=%s)",
            request.url.path,
            request.method,
            bool(extracted_csrf),
            bool(session_id),
        )
        raise HTTPException(
            status_code=403,
            detail="CSRF token validation failed. Please refresh the page and try again.",
        )

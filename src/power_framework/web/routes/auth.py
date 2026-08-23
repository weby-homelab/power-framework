"""Authentication routes for session login and logout."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from ..auth.csrf import get_csrf_token, validate_csrf, verify_csrf_token
from ..auth.password import is_auth_configured, verify_password
from ..auth.rate_limiter import global_login_rate_limiter
from ..auth.session import SessionManager
from ..config import Settings, get_settings
from ..i18n import get_request_lang, translate

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_view(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Render login form with request-bound CSRF token."""
    templates: Jinja2Templates = request.app.state.templates
    get_csrf_token(request, settings)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "settings": settings,
        },
    )


@router.post("/login")
async def login_action(
    request: Request,
    password: str = Form(...),
    csrf_token: str | None = Form(None),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Verify password and set signed session cookie with throttling and CSRF protection."""
    templates: Jinja2Templates = request.app.state.templates
    lang = get_request_lang(request)
    client_ip = request.client.host if request.client else "127.0.0.1"

    if not settings.auth_enabled:
        return RedirectResponse(url="/dashboard", status_code=303)

    is_locked, remaining = global_login_rate_limiter.is_locked(client_ip)
    if is_locked:
        logger.warning("Locked out client %s attempted login (%ds remaining)", client_ip, remaining)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": f"Too many failed login attempts. Please wait {remaining} seconds before trying again.",
                "settings": settings,
            },
            status_code=429,
        )

    # Validate CSRF token for login
    session_id = request.cookies.get(settings.session_cookie_name) or request.cookies.get(
        settings.csrf_cookie_name
    )
    if (
        not session_id
        or not csrf_token
        or not verify_csrf_token(settings.secret_key, session_id, csrf_token)
    ):
        logger.warning("Login CSRF verification failed from client %s", client_ip)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Invalid or expired CSRF token. Please refresh the page and try again.",
                "settings": settings,
            },
            status_code=403,
        )

    # Fail closed if auth is enabled but credentials are not configured
    if not is_auth_configured(settings):
        logger.critical("Authentication enabled but no password or hash configured! Fail-closed.")
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Authentication server error: Administrator credentials unconfigured (fail-closed).",
                "settings": settings,
            },
            status_code=500,
        )

    # Constant-time verification against plain password or hash
    if not verify_password(password, settings.admin_password, settings.admin_password_hash):
        failure_count, is_now_locked, lockout_dur = global_login_rate_limiter.record_failure(
            client_ip
        )
        if is_now_locked:
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={
                    "error": f"Account locked due to {failure_count} failed attempts. Locked for {lockout_dur}s.",
                    "settings": settings,
                },
                status_code=429,
            )
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": translate("invalid_password", lang),
                "settings": settings,
            },
            status_code=401,
        )

    # Successful authentication
    global_login_rate_limiter.record_success(client_ip)
    session_mgr = SessionManager(settings.secret_key)
    auth_session = session_mgr.create_session("admin")

    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=auth_session,
        httponly=True,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        secure=settings.cookie_secure,
        max_age=settings.session_max_age_seconds,
    )
    return response


@router.get("/set-lang")
async def set_language(
    lang: str = "en",
) -> RedirectResponse:
    """Set language preference in cookie and return to the fixed dashboard route."""
    clean_lang = "uk" if lang.lower() in {"uk", "ua", "ukr"} else "en"
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key="power_web_lang",
        value=clean_lang,
        max_age=31536000,
        httponly=False,
        samesite="lax",
    )
    return response


@router.get("/set-theme")
async def set_theme(
    theme: str = "dark",
) -> RedirectResponse:
    """Set theme preference and return to the fixed dashboard route."""
    clean_theme = "light" if theme.lower() in {"light", "day", "white"} else "dark"
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key="power_web_theme",
        value=clean_theme,
        max_age=31536000,
        httponly=False,
        samesite="lax",
    )
    return response


@router.post("/logout", dependencies=[Depends(validate_csrf)])
async def logout_action(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Clear session cookie and redirect to login."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key=settings.session_cookie_name)
    return response

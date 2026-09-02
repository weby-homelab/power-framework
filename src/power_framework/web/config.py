"""Configuration settings for the POWER Web UI."""

from __future__ import annotations

import os
import re
import secrets
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .auth.csrf import verify_csrf_token
from .auth.session import SessionManager

if TYPE_CHECKING:
    from .clients.power import PowerClient


_COOKIE_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def _default_vault_path() -> Path:
    """Resolve default vault path across local dev, Docker, and environment variables."""
    for env_var in ("POWER_WEB_VAULT_PATH", "POWER_VAULT_DIR"):
        val = os.environ.get(env_var)
        if val:
            return Path(val).expanduser().resolve()
    if Path("/brain").exists():
        return Path("/brain")
    cwd_brain = Path.cwd() / "brain"
    if cwd_brain.exists():
        return cwd_brain
    return Path.cwd()


class Settings(BaseSettings):
    """Fail-closed configuration settings for the POWER Web UI."""

    vault_path: Path = Field(
        default_factory=_default_vault_path,
        description="Path to the authoritative Markdown knowledge vault",
    )
    host: str = Field(default="127.0.0.1", description="Bind interface")
    port: int = Field(default=8080, ge=1, le=65535, description="Bind port")
    secret_key: str = Field(
        default_factory=lambda: secrets.token_hex(32),
        description="Secret key for signing sessions and CSRF tokens",
    )
    auth_enabled: bool = Field(
        default=True,
        description="Enable authentication requirements (redirects to /login)",
    )
    admin_password: str = Field(
        default="",
        description="Password for web access",
    )
    admin_password_hash: str | None = Field(
        default=None,
        description="Optional password hash for local web access",
    )

    session_cookie_name: str = "power_web_session"
    csrf_cookie_name: str = "power_web_csrf"
    cookie_secure: bool = True
    cookie_samesite: str = "lax"
    session_max_age_seconds: int = Field(default=86400, ge=300, le=604800)
    max_upload_bytes: int = Field(default=5_000_000, ge=1024, le=50_000_000)
    power_call_timeout_seconds: float = Field(default=30.0, ge=0.1, le=300.0)
    power_call_max_concurrency: int = Field(default=8, ge=1, le=128)
    sse_max_lifetime_seconds: int = Field(default=3600, ge=60, le=86400)
    sse_max_connections: int = Field(default=16, ge=1, le=1000)
    hsts_enabled: bool = True
    read_only_mode: bool = False
    federation_nodes: str = Field(
        default="",
        description="Optional JSON string of custom federated nodes to probe",
    )

    model_config = SettingsConfigDict(
        env_prefix="POWER_WEB_",
        env_file=".env",
        extra="ignore",
    )

    @field_validator("session_cookie_name", "csrf_cookie_name")
    @classmethod
    def validate_cookie_name(cls, value: str) -> str:
        """Accept only RFC token cookie names used by Starlette safely."""
        if _COOKIE_NAME_RE.fullmatch(value) is None:
            raise ValueError("cookie name must contain only RFC token characters")
        return value


@lru_cache
def get_global_settings() -> Settings:
    """Return cached fallback global settings instance."""
    return Settings()


def get_settings(request: Request) -> Settings:
    """Get active Settings from current request app state."""
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        raise RuntimeError("application settings are missing or malformed")
    return settings


def get_client(request: Request) -> PowerClient:
    """Get PowerClient instance using active application settings."""
    from .clients.power import PowerClient

    settings: Settings = get_settings(request)
    return PowerClient(settings.vault_path)


def require_mutation_enabled(request: Request) -> None:
    """Reject mutation routes when the Web UI is configured read-only."""
    if get_settings(request).read_only_mode:
        raise HTTPException(status_code=405, detail="P.O.W.E.R Web UI is in read-only mode")


async def require_mutation_csrf(request: Request) -> None:
    """Require the canonical CSRF dependency unless read-only already stopped it."""
    settings = get_settings(request)
    session_token = request.cookies.get(settings.session_cookie_name)
    csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
    if not session_token or not csrf_cookie:
        raise HTTPException(status_code=403, detail="CSRF token required")
    session_id = SessionManager(settings.secret_key).verify_session(session_token)
    if not session_id:
        raise HTTPException(status_code=403, detail="Invalid session")
    form = await request.form()
    submitted = form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not isinstance(submitted, str) or not verify_csrf_token(
        settings.secret_key, session_id, submitted
    ):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

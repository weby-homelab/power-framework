"""Dependency-light checks shared by the public MCP launcher and server."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from power_framework.core import validate_vault_path

if TYPE_CHECKING:
    from pathlib import Path


def require_configured_vault_root() -> Path:
    """Require one existing, explicitly configured vault directory."""
    configured_root = os.getenv("POWER_VAULT_DIR") or os.getenv("POWER_VAULT_PATH")
    if not configured_root:
        raise RuntimeError(
            "POWER_VAULT_DIR (or POWER_VAULT_PATH) must be configured before starting the MCP server"
        )
    try:
        return validate_vault_path(configured_root)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise RuntimeError("POWER_VAULT_DIR must reference an existing vault directory") from exc

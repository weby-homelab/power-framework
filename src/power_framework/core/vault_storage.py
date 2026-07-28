"""Stable vault identity and isolated local storage paths."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .utils import atomic_write, get_cache_dir

VAULT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class VaultIdentity:
    """Non-sensitive stable identity for one Markdown vault."""

    vault_id: str
    schema_version: int
    created_at: str


def _identity_path(vault_dir: Path) -> Path:
    return vault_dir / ".power" / "vault.json"


def ensure_vault_identity(vault_dir: Path) -> VaultIdentity:
    """Load or atomically create the stable identity stored inside a vault."""
    root = Path(vault_dir).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Vault path is not a directory: {root}")
    identity_path = _identity_path(root)
    if identity_path.exists():
        try:
            raw = json.loads(identity_path.read_text(encoding="utf-8"))
            identity = VaultIdentity(
                vault_id=str(raw["vault_id"]),
                schema_version=int(raw["schema_version"]),
                created_at=str(raw["created_at"]),
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"Invalid vault identity at {identity_path}") from exc
        try:
            uuid.UUID(identity.vault_id)
        except ValueError as exc:
            raise ValueError(f"Invalid vault UUID at {identity_path}") from exc
        if identity.schema_version != VAULT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported vault identity schema at {identity_path}")
        return identity

    identity = VaultIdentity(
        vault_id=str(uuid.uuid4()),
        schema_version=VAULT_SCHEMA_VERSION,
        created_at=datetime.now(UTC).isoformat(),
    )
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(
        identity_path,
        json.dumps(
            {
                "vault_id": identity.vault_id,
                "schema_version": identity.schema_version,
                "created_at": identity.created_at,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return identity


def vault_cache_dir(vault_dir: Path) -> Path:
    """Return the non-sensitive cache namespace for one vault identity."""
    identity = ensure_vault_identity(vault_dir)
    path = get_cache_dir() / "vaults" / identity.vault_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def vault_db_path(vault_dir: Path | None = None) -> Path:
    """Resolve an isolated search database, honoring the explicit test override."""
    override = os.getenv("POWER_SEARCH_DB")
    if override:
        return Path(override)
    if vault_dir is None:
        raise ValueError("A vault path is required when POWER_SEARCH_DB is not set")
    return vault_cache_dir(vault_dir) / "search.db"

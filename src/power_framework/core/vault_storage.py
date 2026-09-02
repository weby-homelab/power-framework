"""Stable vault identity and isolated local storage paths."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .utils import atomic_write, get_cache_dir, vault_control_dir

VAULT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class VaultIdentity:
    """Non-sensitive stable identity for one Markdown vault."""

    vault_id: str
    schema_version: int
    created_at: str


def _identity_path(vault_dir: Path, *, create: bool = False) -> Path:
    return vault_control_dir(vault_dir, create=create) / "vault.json"


def _load_vault_identity(identity_path: Path) -> VaultIdentity:
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


def ensure_vault_identity(vault_dir: Path) -> VaultIdentity:
    """Load or atomically create the stable identity stored inside a vault."""
    root = Path(vault_dir).expanduser().resolve()
    identity_path = _identity_path(root, create=True)
    if identity_path.exists():
        return _load_vault_identity(identity_path)

    identity = VaultIdentity(
        vault_id=str(uuid.uuid4()),
        schema_version=VAULT_SCHEMA_VERSION,
        created_at=datetime.now(UTC).isoformat(),
    )
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


def read_vault_identity(vault_dir: Path) -> VaultIdentity | None:
    """Read an existing vault identity without creating vault state."""
    root = Path(vault_dir).expanduser().resolve()
    if not root.is_dir():
        return None
    identity_path = _identity_path(root)
    if not identity_path.is_file():
        return None
    return _load_vault_identity(identity_path)


CACHE_SOURCE_FILE = "source.json"


def _write_cache_source(namespace: Path, vault_dir: Path, vault_id: str) -> None:
    """Record which vault a cache namespace belongs to.

    Vault identity is one-directional: the vault stores its UUID, the cache is
    named after it. Without a back-reference nothing can decide whether a
    namespace is still live, so a vault that is deleted — a temporary test
    vault, a scratch copy — leaves a namespace no tooling can ever attribute.
    """
    source = namespace / CACHE_SOURCE_FILE
    if source.exists():
        return
    with contextlib.suppress(OSError, ValueError):
        atomic_write(
            source,
            json.dumps(
                {"vault_id": vault_id, "vault_path": str(vault_dir), "schema_version": 1},
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )


def read_cache_source(namespace: Path) -> dict[str, str] | None:
    """Return the recorded source of a cache namespace, or None when unknown."""
    source = namespace / CACHE_SOURCE_FILE
    if not source.is_file():
        return None
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    vault_id = raw.get("vault_id")
    vault_path = raw.get("vault_path")
    schema_version = raw.get("schema_version")
    if (
        not isinstance(vault_id, str)
        or not isinstance(vault_path, str)
        or not vault_path.strip()
        or not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
    ):
        return None
    try:
        uuid.UUID(vault_id)
    except ValueError:
        return None
    if not Path(vault_path).expanduser().is_absolute():
        return None
    return {"vault_id": vault_id, "vault_path": vault_path, "schema_version": str(schema_version)}


def vault_cache_dir(vault_dir: Path) -> Path:
    """Return the non-sensitive cache namespace for one vault identity."""
    identity = ensure_vault_identity(vault_dir)
    path = get_cache_dir() / "vaults" / identity.vault_id
    path.mkdir(parents=True, exist_ok=True)
    _write_cache_source(path, Path(vault_dir).expanduser().resolve(), identity.vault_id)
    return path


def existing_vault_cache_dir(vault_dir: Path) -> Path | None:
    """Return an existing cache namespace without creating any state."""
    identity = read_vault_identity(vault_dir)
    if identity is None:
        return None
    return get_cache_dir(create=False) / "vaults" / identity.vault_id


def existing_vault_db_path(
    vault_dir: Path | None = None,
    *,
    allow_search_db_override: bool = True,
) -> Path | None:
    """Return an existing vault database path without creating a namespace.

    ``POWER_SEARCH_DB`` is retained for controlled local tests and developer
    workflows. Read-only service boundaries can opt out so an inherited process
    environment cannot redirect their reads into a caller-selected database.
    """
    override = os.getenv("POWER_SEARCH_DB")
    if allow_search_db_override and override:
        return Path(override)
    if vault_dir is None:
        raise ValueError("A vault path is required when POWER_SEARCH_DB is not set")
    cache_dir = existing_vault_cache_dir(vault_dir)
    return cache_dir / "search.db" if cache_dir is not None else None


def vault_db_path(vault_dir: Path | None = None) -> Path:
    """Resolve an isolated search database, honoring the explicit test override."""
    override = os.getenv("POWER_SEARCH_DB")
    if override:
        return Path(override)
    if vault_dir is None:
        raise ValueError("A vault path is required when POWER_SEARCH_DB is not set")
    return vault_cache_dir(vault_dir) / "search.db"


@dataclass(frozen=True)
class CacheNamespace:
    """One cache namespace and the verdict about the vault behind it."""

    vault_id: str
    path: Path
    size_bytes: int
    verdict: str  # "live" | "stale" | "unknown"
    detail: str


def _namespace_size(namespace: Path) -> int:
    total = 0
    for filepath in namespace.rglob("*"):
        if not filepath.is_file():
            continue
        try:
            total += filepath.stat().st_size
        except OSError:
            continue
    return total


def classify_cache_namespaces() -> list[CacheNamespace]:
    """Classify every cache namespace as live, stale, or unattributable.

    ``stale`` requires proof: the recorded vault is gone, or it now carries a
    different identity. ``unknown`` covers namespaces written before the
    back-reference existed — they are reported, never assumed dead.
    """
    root = get_cache_dir(create=False) / "vaults"
    if not root.is_dir():
        return []

    namespaces: list[CacheNamespace] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        source = read_cache_source(entry)
        if source is None:
            namespaces.append(
                CacheNamespace(
                    entry.name, entry, _namespace_size(entry), "unknown", "no source record"
                )
            )
            continue

        if source["vault_id"] != entry.name:
            namespaces.append(
                CacheNamespace(
                    entry.name,
                    entry,
                    _namespace_size(entry),
                    "unknown",
                    "source identity does not match namespace",
                )
            )
            continue

        vault_path = Path(source["vault_path"]).expanduser()
        if not vault_path.is_dir():
            verdict, detail = "stale", f"vault gone: {vault_path}"
        else:
            try:
                identity = read_vault_identity(vault_path)
            except (OSError, ValueError, NotADirectoryError) as exc:
                verdict, detail = "unknown", f"identity unreadable: {exc}"
            else:
                if identity is None:
                    verdict, detail = "unknown", "vault identity missing"
                elif identity.vault_id == entry.name:
                    verdict, detail = "live", str(vault_path)
                else:
                    verdict, detail = "stale", f"vault re-identified: {vault_path}"
        namespaces.append(
            CacheNamespace(entry.name, entry, _namespace_size(entry), verdict, detail)
        )
    return namespaces


def prune_vault_caches(*, dry_run: bool = True, include_unknown: bool = False) -> str:
    """Remove cache namespaces whose vault is provably gone. Returns a report."""
    namespaces = classify_cache_namespaces()
    targets = [n for n in namespaces if n.verdict == "stale"]
    unknown = [n for n in namespaces if n.verdict == "unknown"]
    if include_unknown:
        targets += unknown

    removed = 0
    freed = 0
    if not dry_run:
        for namespace in targets:
            try:
                shutil.rmtree(namespace.path)
            except OSError:
                continue
            removed += 1
            freed += namespace.size_bytes

    live = [n for n in namespaces if n.verdict == "live"]
    lines = [
        "=== Cache Prune ===",
        f"Mode: {'DRY RUN' if dry_run else 'LIVE'}",
        f"Namespaces: {len(namespaces)} (live {len(live)}, stale {len(namespaces) - len(live) - len(unknown)}, unknown {len(unknown)})",
        f"{'Would remove' if dry_run else 'Removed'}: {len(targets) if dry_run else removed}"
        f" ({(sum(n.size_bytes for n in targets) if dry_run else freed) / 1024 / 1024:.1f} MB)",
        "",
    ]
    lines.extend(
        f"  {namespace.vault_id}  {namespace.size_bytes / 1024:.0f} KB  {namespace.detail}"
        for namespace in targets[:20]
    )
    if len(targets) > 20:
        lines.append(f"  ... and {len(targets) - 20} more")
    if unknown and not include_unknown:
        lines.append("")
        lines.append(
            f"{len(unknown)} namespace(s) predate the source record and cannot be attributed. "
            "Re-run with --include-unknown to remove them as well."
        )
    return "\n".join(lines) + "\n"

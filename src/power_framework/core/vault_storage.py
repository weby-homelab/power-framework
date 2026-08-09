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
    return raw if isinstance(raw, dict) else None


def vault_cache_dir(vault_dir: Path) -> Path:
    """Return the non-sensitive cache namespace for one vault identity."""
    identity = ensure_vault_identity(vault_dir)
    path = get_cache_dir() / "vaults" / identity.vault_id
    path.mkdir(parents=True, exist_ok=True)
    _write_cache_source(path, Path(vault_dir).expanduser().resolve(), identity.vault_id)
    return path


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
    return sum(f.stat().st_size for f in namespace.rglob("*") if f.is_file())


def classify_cache_namespaces() -> list[CacheNamespace]:
    """Classify every cache namespace as live, stale, or unattributable.

    ``stale`` requires proof: the recorded vault is gone, or it now carries a
    different identity. ``unknown`` covers namespaces written before the
    back-reference existed — they are reported, never assumed dead.
    """
    root = get_cache_dir() / "vaults"
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

        vault_path = Path(str(source.get("vault_path", "")))
        if not vault_path.is_dir():
            verdict, detail = "stale", f"vault gone: {vault_path}"
        else:
            try:
                current = ensure_vault_identity(vault_path).vault_id
            except (OSError, ValueError, NotADirectoryError) as exc:
                verdict, detail = "unknown", f"identity unreadable: {exc}"
            else:
                if current == entry.name:
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

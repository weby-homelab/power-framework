"""Incremental reconciliation for staging generations when sources change mid-sync."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

logger = logging.getLogger(__name__)

MAX_SNAPSHOT_RECONCILE_ROUNDS = 3


@dataclass(frozen=True)
class _ReconcileOps:
    """Injected generation-index primitives so reconciliation stays acyclic."""

    sync_vault_to_db: Callable[..., Any]
    assert_snapshot_unchanged: Callable[[Path, Any], None]
    source_inventory: Callable[[Path], Any]
    state_db_path: Callable[[Path], Path]
    init_state_db: Callable[[sqlite3.Connection], None]
    error_cls: type[Exception]


def _snapshot_hash(sources: dict[str, str]) -> str:
    digest = hashlib.blake2b(digest_size=32)
    for rel_path, content_hash in sorted(sources.items()):
        digest.update(rel_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _enforce_partial_policy(
    inventory: Any, allow_partial: bool, error_cls: type[Exception]
) -> None:
    """Fail closed with source diagnostics when invalid notes exist and partial sync is off."""
    if inventory.invalid_sources and not allow_partial:
        details = "; ".join(
            f"{rel_path} ({reason})"
            for rel_path, reason in sorted(inventory.invalid_sources.items())
        )
        raise error_cls(
            f"sync failed closed: {len(inventory.invalid_sources)} source(s) excluded; {details}"
        )


def _update_building_snapshot(
    state_db_path: Path,
    generation_id: str,
    snapshot_hash: str,
    inventory: Any,
    ops: _ReconcileOps,
) -> None:
    """Update the in-flight building record to reflect a reconciled source snapshot."""
    with closing(sqlite3.connect(state_db_path, timeout=30)) as state_conn:
        ops.init_state_db(state_conn)
        state_conn.execute("BEGIN IMMEDIATE")
        try:
            cur = state_conn.execute(
                """
                UPDATE index_generations
                SET source_snapshot_hash = ?, expected_files = ?, total_scanned = ?,
                    invalid_sources = ?
                WHERE generation_id = ? AND state = 'building'
                """,
                (
                    snapshot_hash,
                    len(inventory.valid_sources),
                    inventory.total_scanned,
                    len(inventory.invalid_sources),
                    generation_id,
                ),
            )
            if cur.rowcount != 1:
                raise ops.error_cls(
                    f"generation {generation_id} lost its active 'building' lease during reconciliation"
                )
            state_conn.execute(
                "DELETE FROM generation_sources WHERE generation_id = ?", (generation_id,)
            )
            state_conn.executemany(
                "INSERT INTO generation_sources (generation_id, rel_path, content_hash) VALUES (?, ?, ?)",
                [
                    (generation_id, path, content_hash)
                    for path, content_hash in inventory.valid_sources.items()
                ],
            )
            state_conn.execute(
                "DELETE FROM generation_invalid_sources WHERE generation_id = ?",
                (generation_id,),
            )
            state_conn.executemany(
                """
                INSERT INTO generation_invalid_sources (generation_id, path_hash, reason)
                VALUES (?, ?, ?)
                """,
                [
                    (
                        generation_id,
                        hashlib.sha256(path.encode("utf-8")).hexdigest(),
                        reason,
                    )
                    for path, reason in inventory.invalid_sources.items()
                ],
            )
            state_conn.commit()
        except Exception:
            state_conn.rollback()
            raise


def reconcile_staging_snapshot(
    root: Path,
    conn: sqlite3.Connection,
    *,
    generation_id: str,
    inventory: Any,
    snapshot_hash: str,
    sync_embeddings: bool,
    force_rebuild: bool,
    allow_partial: bool,
    ops: _ReconcileOps,
    max_rounds: int = MAX_SNAPSHOT_RECONCILE_ROUNDS,
) -> tuple[Any, str]:
    """Build staging rows and reconcile concurrent source edits without losing embeddings.

    When a source note changes during a long embedding pass, discarding the whole
    staging database forces subsequent runs to re-embed already completed notes.
    Instead, take a fresh inventory, invalidate ``file_metadata.mtime`` only for
    notes whose BLAKE2 content hash changed, and re-run ``_sync_vault_to_db`` on the
    same staging connection (with ``force_rebuild=False``) up to ``max_rounds``.
    """
    if max_rounds < 1:
        raise ops.error_cls("max_rounds must be >= 1")

    current_inventory = inventory
    current_hash = snapshot_hash
    for attempt in range(max_rounds):
        ops.sync_vault_to_db(
            root,
            conn,
            sync_embeddings=sync_embeddings,
            force_rebuild=force_rebuild if attempt == 0 else False,
        )
        try:
            ops.assert_snapshot_unchanged(root, current_inventory)
            return current_inventory, current_hash
        except ops.error_cls as exc:
            if (
                not str(exc).startswith("source snapshot changed during sync")
                or attempt + 1 >= max_rounds
            ):
                raise
            next_inventory = ops.source_inventory(root)
            try:
                _enforce_partial_policy(next_inventory, allow_partial, ops.error_cls)
            except ops.error_cls as policy_exc:
                raise policy_exc from exc
            stale_paths = [
                path
                for path, digest in next_inventory.valid_sources.items()
                if current_inventory.valid_sources.get(path) != digest
            ]
            stale_paths.extend(
                path
                for path in current_inventory.valid_sources
                if path in next_inventory.invalid_sources
            )
            if stale_paths:
                conn.executemany(
                    "UPDATE file_metadata SET mtime = -1 WHERE rel_path = ?",
                    [(path,) for path in stale_paths],
                )
                conn.commit()
            next_hash = _snapshot_hash(next_inventory.valid_sources)
            _update_building_snapshot(
                ops.state_db_path(root),
                generation_id,
                next_hash,
                next_inventory,
                ops,
            )
            logger.info(
                "Reconciling staging generation %s after concurrent source edits "
                "(round %d/%d, changed=%d)",
                generation_id,
                attempt + 2,
                max_rounds,
                len(stale_paths),
            )
            current_inventory = next_inventory
            current_hash = next_hash

    return current_inventory, current_hash  # pragma: no cover - loop returns or raises

"""Atomic, per-vault publication of search-index generations."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .db import _init_db
from .ignore import should_skip
from .parser import read_file_content, validate_metadata
from .vault_storage import ensure_vault_identity, vault_cache_dir, vault_db_path


class IndexGenerationError(RuntimeError):
    """A staged index did not meet the active-generation publication contract."""


@dataclass(frozen=True)
class GenerationReport:
    """Evidence returned only after a generation becomes active."""

    generation_id: str
    source_snapshot_hash: str
    expected_files: int
    actual_files: int
    actual_chunks: int


def _state_db_path(vault_dir: Path) -> Path:
    return vault_cache_dir(vault_dir) / "generation-state.db"


def _init_state_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS index_generations (
            generation_id TEXT PRIMARY KEY,
            state TEXT NOT NULL CHECK (state IN ('building', 'ready', 'failed', 'superseded')),
            source_snapshot_hash TEXT NOT NULL,
            expected_files INTEGER NOT NULL,
            actual_files INTEGER NOT NULL DEFAULT 0,
            actual_chunks INTEGER NOT NULL DEFAULT 0,
            embedding_provider TEXT,
            embedding_model TEXT,
            chunker_identity TEXT NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS generation_sources (
            generation_id TEXT NOT NULL,
            rel_path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            PRIMARY KEY (generation_id, rel_path),
            FOREIGN KEY (generation_id) REFERENCES index_generations(generation_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS active_generation (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            generation_id TEXT NOT NULL,
            activated_at TEXT NOT NULL,
            FOREIGN KEY (generation_id) REFERENCES index_generations(generation_id)
        )
        """
    )
    conn.commit()


def _valid_sources(vault_dir: Path) -> dict[str, str]:
    """Hash every valid source before staging so coverage is content-based."""
    sources: dict[str, str] = {}
    for path in sorted(vault_dir.rglob("*.md")):
        if path.name in {"index.md", "log.md", "_index.md"}:
            continue
        rel_path = str(path.relative_to(vault_dir))
        if should_skip(vault_dir, rel_path):
            continue
        content = read_file_content(path)
        if validate_metadata(content) is None:
            continue
        sources[rel_path] = hashlib.blake2b(content.encode("utf-8"), digest_size=32).hexdigest()
    return sources


def _snapshot_hash(sources: dict[str, str]) -> str:
    digest = hashlib.blake2b(digest_size=32)
    for rel_path, content_hash in sources.items():
        digest.update(rel_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _assert_source_snapshot_unchanged(vault_dir: Path, expected_sources: dict[str, str]) -> None:
    """Reject a build when source content changed after staging began.

    A path-only coverage check cannot prove that the staged rows describe the
    current vault: a note can change while embedding is in progress. Compare
    BLAKE2 identities again immediately before publication so callers retry
    instead of activating a stale generation.
    """
    current_sources = _valid_sources(vault_dir)
    if current_sources == expected_sources:
        return

    changed_paths = sorted(set(expected_sources) | set(current_sources))
    details = [
        f"{path}:{expected_sources.get(path, 'missing')}->{current_sources.get(path, 'missing')}"
        for path in changed_paths
        if expected_sources.get(path) != current_sources.get(path)
    ]
    raise IndexGenerationError(
        "source snapshot changed during sync; retry required; changed=" + ", ".join(details[:10])
    )


def _record_building(
    vault_dir: Path, generation_id: str, snapshot_hash: str, sources: dict[str, str]
) -> None:
    with sqlite3.connect(_state_db_path(vault_dir), timeout=30) as conn:
        _init_state_db(conn)
        conn.execute(
            """
            INSERT INTO index_generations (
                generation_id, state, source_snapshot_hash, expected_files,
                chunker_identity, created_at
            ) VALUES (?, 'building', ?, ?, ?, ?)
            """,
            (
                generation_id,
                snapshot_hash,
                len(sources),
                "SemanticChunker/v1",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.executemany(
            "INSERT INTO generation_sources (generation_id, rel_path, content_hash) VALUES (?, ?, ?)",
            [(generation_id, path, content_hash) for path, content_hash in sources.items()],
        )
        conn.commit()


def _record_failure(vault_dir: Path, generation_id: str, error: str) -> None:
    with sqlite3.connect(_state_db_path(vault_dir), timeout=30) as conn:
        _init_state_db(conn)
        conn.execute(
            """
            UPDATE index_generations
            SET state = 'failed', error = ?, completed_at = ?
            WHERE generation_id = ?
            """,
            (error[:4000], datetime.now(timezone.utc).isoformat(), generation_id),
        )
        conn.commit()


def _publish(
    vault_dir: Path,
    generation_id: str,
    staging_path: Path,
    actual_files: int,
    actual_chunks: int,
    embedding_provider: str | None,
    embedding_model: str | None,
) -> None:
    """Atomically replace the active DB only after the staged DB is complete."""
    active_path = vault_db_path(vault_dir)
    active_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging_path, active_path)
    with sqlite3.connect(_state_db_path(vault_dir), timeout=30) as conn:
        _init_state_db(conn)
        conn.execute("UPDATE index_generations SET state = 'superseded' WHERE state = 'ready'")
        conn.execute(
            """
            UPDATE index_generations
            SET state = 'ready', actual_files = ?, actual_chunks = ?,
                embedding_provider = ?, embedding_model = ?, completed_at = ?
            WHERE generation_id = ?
            """,
            (
                actual_files,
                actual_chunks,
                embedding_provider,
                embedding_model,
                datetime.now(timezone.utc).isoformat(),
                generation_id,
            ),
        )
        conn.execute(
            """
            INSERT INTO active_generation (id, generation_id, activated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET generation_id = excluded.generation_id,
                activated_at = excluded.activated_at
            """,
            (generation_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def _validate_staging(
    conn: sqlite3.Connection, expected_paths: set[str], sync_embeddings: bool
) -> tuple[int, int, str | None, str | None]:
    actual_paths = {row[0] for row in conn.execute("SELECT rel_path FROM file_metadata")}
    missing = sorted(expected_paths - actual_paths)
    extra = sorted(actual_paths - expected_paths)
    if missing or extra:
        raise IndexGenerationError(
            f"source coverage mismatch: missing={missing[:10]} extra={extra[:10]}"
        )
    actual_chunks = int(conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0])
    if sync_embeddings:
        chunk_paths = {
            row[0] for row in conn.execute("SELECT DISTINCT rel_path FROM chunk_embeddings")
        }
        dense_missing = sorted(expected_paths - chunk_paths)
        if dense_missing:
            raise IndexGenerationError(f"dense coverage mismatch: missing={dense_missing[:10]}")
        manifest = dict(
            conn.execute("SELECT manifest_key, manifest_value FROM dense_index_manifest")
        )
        if manifest.get("chunk_count") != str(actual_chunks):
            raise IndexGenerationError("dense manifest count does not match staged chunk count")
        provider = manifest.get("embedding_provider")
        model = manifest.get("embedding_model")
    else:
        provider = None
        model = None
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise IndexGenerationError(f"SQLite integrity check failed: {integrity}")
    return len(actual_paths), actual_chunks, provider, model


def sync_vault_atomically(
    vault_dir: Path, *, sync_embeddings: bool, force_rebuild: bool = False
) -> GenerationReport:
    """Build a complete staged generation and atomically publish it on success."""
    root = Path(vault_dir).expanduser().resolve()
    ensure_vault_identity(root)
    sources = _valid_sources(root)
    snapshot_hash = _snapshot_hash(sources)
    generation_id = str(uuid.uuid4())
    _record_building(root, generation_id, snapshot_hash, sources)
    staging_dir = vault_cache_dir(root) / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    staging_path = staging_dir / f"{generation_id}.db"

    try:
        from .searcher import _sync_vault_to_db

        with sqlite3.connect(staging_path, timeout=30) as conn:
            _init_db(conn)
            _sync_vault_to_db(
                root,
                conn,
                sync_embeddings=sync_embeddings,
                force_rebuild=force_rebuild,
            )
            _assert_source_snapshot_unchanged(root, sources)
            actual_files, actual_chunks, provider, model = _validate_staging(
                conn, set(sources), sync_embeddings
            )
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        _publish(
            root,
            generation_id,
            staging_path,
            actual_files,
            actual_chunks,
            provider,
            model,
        )
    except Exception as exc:
        _record_failure(root, generation_id, str(exc))
        for path in (
            staging_path,
            staging_path.with_suffix(".db-wal"),
            staging_path.with_suffix(".db-shm"),
        ):
            path.unlink(missing_ok=True)
        if isinstance(exc, IndexGenerationError):
            raise
        raise IndexGenerationError(f"generation {generation_id} failed: {exc}") from exc

    return GenerationReport(
        generation_id=generation_id,
        source_snapshot_hash=snapshot_hash,
        expected_files=len(sources),
        actual_files=actual_files,
        actual_chunks=actual_chunks,
    )

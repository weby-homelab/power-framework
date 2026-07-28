"""Atomic, per-vault publication of search-index generations."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .db import _init_db
from .ignore import should_skip
from .parser import read_file_content, validate_metadata
from .vault_storage import ensure_vault_identity, vault_cache_dir, vault_db_path


class IndexGenerationError(RuntimeError):
    """A staged index did not meet the active-generation publication contract."""


GENERATION_STORE_SCHEMA_VERSION = 1
RETAIN_READY_GENERATIONS = 2


class ActiveGenerationError(IndexGenerationError):
    """The state store does not resolve to a verified immutable generation."""


@dataclass(frozen=True)
class SourceInventory:
    """The complete source accounting captured before a generation is built."""

    valid_sources: dict[str, str]
    invalid_sources: dict[str, str]
    total_scanned: int


@dataclass(frozen=True)
class GenerationReport:
    """Evidence returned only after a generation becomes active."""

    generation_id: str
    source_snapshot_hash: str
    expected_files: int
    actual_files: int
    actual_chunks: int
    total_scanned: int
    invalid_sources: int


def _state_db_path(vault_dir: Path) -> Path:
    return vault_cache_dir(vault_dir) / "generation-state.db"


def _generation_path(vault_dir: Path, generation_id: str) -> Path:
    return vault_cache_dir(vault_dir) / "generations" / f"{generation_id}.db"


def _add_column_if_missing(conn: sqlite3.Connection, name: str, declaration: str) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(index_generations)")}
    if name not in columns:
        conn.execute(f"ALTER TABLE index_generations ADD COLUMN {name} {declaration}")


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
            total_scanned INTEGER NOT NULL DEFAULT 0,
            invalid_sources INTEGER NOT NULL DEFAULT 0,
            db_sha256 TEXT,
            db_size INTEGER,
            db_schema_version INTEGER,
            error TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        )
        """
    )
    _add_column_if_missing(conn, "total_scanned", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "invalid_sources", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "db_sha256", "TEXT")
    _add_column_if_missing(conn, "db_size", "INTEGER")
    _add_column_if_missing(conn, "db_schema_version", "INTEGER")
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS generation_invalid_sources (
            generation_id TEXT NOT NULL,
            path_hash TEXT NOT NULL,
            reason TEXT NOT NULL,
            PRIMARY KEY (generation_id, path_hash),
            FOREIGN KEY (generation_id) REFERENCES index_generations(generation_id)
        )
        """
    )
    conn.commit()


def _source_inventory(vault_dir: Path) -> SourceInventory:
    """Account for every candidate source before staging begins."""
    valid_sources: dict[str, str] = {}
    invalid_sources: dict[str, str] = {}
    total_scanned = 0
    for path in sorted(vault_dir.rglob("*.md")):
        if path.name in {"index.md", "log.md", "_index.md"}:
            continue
        rel_path = str(path.relative_to(vault_dir))
        if should_skip(vault_dir, rel_path):
            continue
        total_scanned += 1
        try:
            content = read_file_content(path)
        except (OSError, UnicodeError):
            invalid_sources[rel_path] = "read_error"
            continue
        if validate_metadata(content) is None:
            invalid_sources[rel_path] = "invalid_metadata"
            continue
        valid_sources[rel_path] = hashlib.blake2b(
            content.encode("utf-8"), digest_size=32
        ).hexdigest()
    return SourceInventory(valid_sources, invalid_sources, total_scanned)


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
    current_sources = _source_inventory(vault_dir).valid_sources
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
    vault_dir: Path, generation_id: str, snapshot_hash: str, inventory: SourceInventory
) -> None:
    with closing(sqlite3.connect(_state_db_path(vault_dir), timeout=30)) as conn:
        _init_state_db(conn)
        conn.execute(
            """
            INSERT INTO index_generations (
                generation_id, state, source_snapshot_hash, expected_files,
                chunker_identity, total_scanned, invalid_sources, created_at
            ) VALUES (?, 'building', ?, ?, ?, ?, ?, ?)
            """,
            (
                generation_id,
                snapshot_hash,
                len(inventory.valid_sources),
                "SemanticChunker/v1",
                inventory.total_scanned,
                len(inventory.invalid_sources),
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.executemany(
            "INSERT INTO generation_sources (generation_id, rel_path, content_hash) VALUES (?, ?, ?)",
            [
                (generation_id, path, content_hash)
                for path, content_hash in inventory.valid_sources.items()
            ],
        )
        conn.executemany(
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
        conn.commit()


def _record_failure(vault_dir: Path, generation_id: str, error: str) -> None:
    with closing(sqlite3.connect(_state_db_path(vault_dir), timeout=30)) as conn:
        _init_state_db(conn)
        conn.execute(
            """
            UPDATE index_generations
            SET state = 'failed', error = ?, completed_at = ?
            WHERE generation_id = ?
            """,
            (error[:4000], datetime.now(UTC).isoformat(), generation_id),
        )
        conn.commit()


def _file_identity(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest(), path.stat().st_size


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:  # pragma: no cover - platforms without directory fsync
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _verified_generation_path(
    vault_dir: Path,
    generation_id: str,
    expected_sha256: str,
    expected_size: int,
) -> Path:
    path = _generation_path(vault_dir, generation_id)
    if not path.is_file():
        raise ActiveGenerationError(f"active generation file is missing: {generation_id}")
    actual_sha256, actual_size = _file_identity(path)
    if actual_size != expected_size or actual_sha256 != expected_sha256:
        raise ActiveGenerationError(f"active generation file identity mismatch: {generation_id}")
    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)) as conn:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.Error as exc:
        raise ActiveGenerationError(f"active generation cannot be read: {generation_id}") from exc
    if integrity != "ok":
        raise ActiveGenerationError(f"active generation integrity check failed: {generation_id}")
    return path


def resolve_active_generation_path(vault_dir: Path) -> Path | None:
    """Resolve the authoritative active generation or fail closed.

    ``None`` means this vault still has no generation-state store and callers
    may use the pre-3.3 legacy DB path. Once a state store has an active row,
    fallback is forbidden: the state pointer and immutable file identity are
    the retrieval contract.
    """
    root = Path(vault_dir).expanduser().resolve()
    if not root.is_dir():
        return None
    state_path = _state_db_path(root)
    if not state_path.exists():
        return None
    try:
        with closing(sqlite3.connect(f"file:{state_path}?mode=ro", uri=True, timeout=30)) as conn:
            row = conn.execute(
                """
                SELECT generation_id, state, db_sha256, db_size
                FROM index_generations
                WHERE generation_id = (SELECT generation_id FROM active_generation WHERE id = 1)
                """
            ).fetchone()
    except sqlite3.Error as exc:
        raise ActiveGenerationError("generation state store is unreadable") from exc
    if row is None:
        return None
    generation_id, state, db_sha256, db_size = row
    if state != "ready" or not db_sha256 or db_size is None:
        raise ActiveGenerationError(f"active generation is not ready: {generation_id}")
    return _verified_generation_path(root, generation_id, str(db_sha256), int(db_size))


def _cleanup_generations(vault_dir: Path) -> None:
    """Best-effort retention, called only after an active-generation readback."""
    with closing(sqlite3.connect(_state_db_path(vault_dir), timeout=30)) as conn:
        _init_state_db(conn)
        rows = conn.execute(
            """
            SELECT generation_id FROM index_generations
            WHERE state = 'ready'
            ORDER BY completed_at DESC, generation_id DESC
            """
        ).fetchall()
        for (generation_id,) in rows[RETAIN_READY_GENERATIONS:]:
            path = _generation_path(vault_dir, generation_id)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue
            conn.execute(
                "UPDATE index_generations SET state = 'superseded' WHERE generation_id = ?",
                (generation_id,),
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
    """Publish a verified immutable DB, then atomically update the state pointer."""
    generation_path = _generation_path(vault_dir, generation_id)
    generation_path.parent.mkdir(parents=True, exist_ok=True)
    if generation_path.exists():
        raise IndexGenerationError(f"generation path already exists: {generation_id}")
    _fsync_file(staging_path)
    os.replace(staging_path, generation_path)
    _fsync_directory(generation_path.parent)
    db_sha256, db_size = _file_identity(generation_path)
    with closing(sqlite3.connect(_state_db_path(vault_dir), timeout=30)) as conn:
        _init_state_db(conn)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE index_generations
                SET state = 'ready', actual_files = ?, actual_chunks = ?,
                    embedding_provider = ?, embedding_model = ?, db_sha256 = ?,
                    db_size = ?, db_schema_version = ?, completed_at = ?
                WHERE generation_id = ?
                """,
                (
                    actual_files,
                    actual_chunks,
                    embedding_provider,
                    embedding_model,
                    db_sha256,
                    db_size,
                    GENERATION_STORE_SCHEMA_VERSION,
                    datetime.now(UTC).isoformat(),
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
                (generation_id, datetime.now(UTC).isoformat()),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    resolved = resolve_active_generation_path(vault_dir)
    if resolved != generation_path:
        raise ActiveGenerationError(f"active generation readback failed: {generation_id}")
    try:
        _cleanup_generations(vault_dir)
    except OSError:
        # Retention is deliberately outside the correctness transaction. A
        # full disk or transient filesystem error may leave extra immutable
        # generations, but it must never roll back or invalidate the pointer.
        return


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


def _archive_legacy_database(vault_dir: Path, legacy_path: Path, generation_id: str) -> None:
    """Archive a legacy fixed DB only after the generation pointer readback."""
    if not legacy_path.exists():
        return
    archive_dir = vault_cache_dir(vault_dir) / "legacy"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"search.db.{generation_id}.bak"
    os.replace(legacy_path, archive_path)
    for suffix in ("-wal", "-shm"):
        legacy_path.with_name(legacy_path.name + suffix).unlink(missing_ok=True)


def _migrate_legacy_database(
    vault_dir: Path,
    inventory: SourceInventory,
    snapshot_hash: str,
    *,
    sync_embeddings: bool,
) -> GenerationReport | None:
    """Import one verified pre-generation fixed DB into the immutable store.

    The explicit ``POWER_SEARCH_DB`` override is a test/developer escape hatch,
    not a vault-owned legacy store, so it is intentionally never migrated.
    """
    if os.getenv("POWER_SEARCH_DB"):
        return None
    if resolve_active_generation_path(vault_dir) is not None:
        return None
    legacy_path = vault_db_path(vault_dir)
    if not legacy_path.is_file():
        return None

    generation_id = str(uuid.uuid4())
    _record_building(vault_dir, generation_id, snapshot_hash, inventory)
    staging_path = vault_cache_dir(vault_dir) / "staging" / f"{generation_id}.db"
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            closing(sqlite3.connect(legacy_path, timeout=30)) as legacy_conn,
            closing(sqlite3.connect(staging_path, timeout=30)) as staging_conn,
        ):
            legacy_conn.backup(staging_conn)
            actual_files, actual_chunks, provider, model = _validate_staging(
                staging_conn, set(inventory.valid_sources), sync_embeddings
            )
            staging_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        _assert_source_snapshot_unchanged(vault_dir, inventory.valid_sources)
        _publish(
            vault_dir,
            generation_id,
            staging_path,
            actual_files,
            actual_chunks,
            provider,
            model,
        )
        _archive_legacy_database(vault_dir, legacy_path, generation_id)
    except Exception as exc:
        _record_failure(vault_dir, generation_id, str(exc))
        for path in (
            staging_path,
            staging_path.with_suffix(".db-wal"),
            staging_path.with_suffix(".db-shm"),
        ):
            path.unlink(missing_ok=True)
        if isinstance(exc, IndexGenerationError):
            raise
        raise IndexGenerationError(f"legacy generation {generation_id} failed: {exc}") from exc

    return GenerationReport(
        generation_id=generation_id,
        source_snapshot_hash=snapshot_hash,
        expected_files=len(inventory.valid_sources),
        actual_files=actual_files,
        actual_chunks=actual_chunks,
        total_scanned=inventory.total_scanned,
        invalid_sources=len(inventory.invalid_sources),
    )


def sync_vault_atomically(
    vault_dir: Path, *, sync_embeddings: bool, force_rebuild: bool = False
) -> GenerationReport:
    """Build a complete staged generation and atomically publish it on success."""
    root = Path(vault_dir).expanduser().resolve()
    ensure_vault_identity(root)
    inventory = _source_inventory(root)
    sources = inventory.valid_sources
    snapshot_hash = _snapshot_hash(sources)
    migrated = _migrate_legacy_database(
        root, inventory, snapshot_hash, sync_embeddings=sync_embeddings
    )
    if migrated is not None:
        return migrated
    generation_id = str(uuid.uuid4())
    _record_building(root, generation_id, snapshot_hash, inventory)
    staging_dir = vault_cache_dir(root) / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    staging_path = staging_dir / f"{generation_id}.db"

    try:
        from .searcher import _sync_vault_to_db

        with closing(sqlite3.connect(staging_path, timeout=30)) as conn:
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
        total_scanned=inventory.total_scanned,
        invalid_sources=len(inventory.invalid_sources),
    )

"""
Background Vault Indexer (Performance Plan §1).

Implements an async-style ingestion queue: the hot search path no longer
synchronizes the vault synchronously. Instead a single background worker
materializes the FTS / embedding index, while searchers read whatever is
already materialized and honestly report staleness via a coverage footer.

Design (Roy Zhu, 2026-06 pattern):
- A ``sync_queue`` table holds a pending request and a ``worker_lease`` row
  guarantees at most one worker runs at a time (lease with timestamp).
- ``ensure_indexer_running`` spawns a daemon thread that drains the queue.
- ``request_sync`` enqueues a sync request (no-op if one is already queued).
- ``get_coverage`` reports indexed / total file counts for the staleness footer.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path

from .db import _init_db
from .ignore import should_skip
from .utils import get_cache_dir

logger = logging.getLogger(__name__)

_index_lock = threading.Lock()
_indexer_thread: threading.Thread | None = None
_indexer_stop = threading.Event()


def _db_path() -> Path:
    """Resolve the search index DB path, honoring POWER_SEARCH_DB override.

    Must match ``searcher._db_path`` so the background indexer and the
    synchronous searcher operate on the same database — and so the
    ``isolated_search_db`` test fixture (which sets POWER_SEARCH_DB) actually
    isolates the indexer too. A prior version ignored the override, causing
    silent cross-test contamination via the shared default DB.
    """
    import os

    override = os.getenv("POWER_SEARCH_DB")
    if override:
        return Path(override)
    return get_cache_dir() / "power_search.db"


def _ensure_queue_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_queue (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            requested_at REAL,
            mode TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS worker_lease (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            leased_at REAL,
            pid INTEGER
        )
        """
    )
    conn.commit()


def request_sync(vault_dir: Path, mode: str = "fts") -> None:
    """Enqueue a background sync request (non-blocking).

    Only one pending request is kept; concurrent callers are no-ops.
    """
    try:
        conn = _connect()
        _ensure_queue_table(conn)
        cur = conn.cursor()
        cur.execute("SELECT id FROM sync_queue WHERE id = 1")
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO sync_queue (id, requested_at, mode) VALUES (1, ?, ?)",
                (time.time(), mode),
            )
        else:
            cur.execute(
                "UPDATE sync_queue SET requested_at = ?, mode = ? WHERE id = 1",
                (time.time(), mode),
            )
        conn.commit()
        conn.close()
    except Exception as e:  # pragma: no cover
        logger.debug("request_sync failed: %s", e)
    ensure_indexer_running()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    _init_db(conn)
    return conn


def ensure_indexer_running() -> None:
    """Start the singleton background indexer thread if not already running."""
    global _indexer_thread
    with _index_lock:
        if _indexer_thread is not None and _indexer_thread.is_alive():
            return
        _indexer_stop.clear()
        _indexer_thread = threading.Thread(
            target=_index_worker_loop, name="power-indexer", daemon=True
        )
        _indexer_thread.start()
        logger.info("Background indexer started")


def stop_indexer() -> None:
    """Signal the background indexer to stop (best-effort)."""
    _indexer_stop.set()


def _try_acquire_lease(conn) -> bool:
    """Acquire the single-worker lease. Returns True if we own it."""
    now = time.time()
    cur = conn.cursor()
    cur.execute("SELECT leased_at, pid FROM worker_lease WHERE id = 1")
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "INSERT INTO worker_lease (id, leased_at, pid) VALUES (1, ?, ?)",
            (now, _pid()),
        )
        conn.commit()
        return True
    leased_at, pid = row
    # Lease expires after 10 min of inactivity (stale worker recovery).
    if now - leased_at > 600 or not _pid_alive(pid):
        cur.execute(
            "UPDATE worker_lease SET leased_at = ?, pid = ? WHERE id = 1",
            (now, _pid()),
        )
        conn.commit()
        return True
    return False


def _release_lease(conn) -> None:
    cur = conn.cursor()
    cur.execute("UPDATE worker_lease SET leased_at = 0 WHERE id = 1")
    conn.commit()


def _index_worker_loop() -> None:
    """Drain the sync queue in the background until stopped."""
    while not _indexer_stop.is_set():
        try:
            conn = _connect()
            _ensure_queue_table(conn)
            cur = conn.cursor()
            cur.execute("SELECT mode FROM sync_queue WHERE id = 1")
            row = cur.fetchone()
            if row is None:
                conn.close()
                if _indexer_stop.wait(2.0):
                    return
                continue

            mode = row[0] if row[0] else "fts"
            conn.close()

            if not _try_acquire_lease(_connect()):
                # Another worker holds the lease; back off.
                if _indexer_stop.wait(2.0):
                    return
                continue

            # Resolve the vault dir from POWER_VAULT_DIR (configured by caller).
            vault = _resolve_vault_dir()
            if vault is None:
                logger.warning("Indexer: no vault dir configured, skipping sync")
                _clear_queue()
                _release_lease(_connect())
                if _indexer_stop.wait(2.0):
                    return
                continue

            sync_embeddings = mode in ("semantic", "hybrid_reranked")
            try:
                from .searcher import _sync_vault_to_db

                wconn = _connect()
                _sync_vault_to_db(vault, wconn, sync_embeddings=sync_embeddings)
                wconn.close()
                logger.info("Background indexer completed sync (mode=%s)", mode)
            except Exception as e:  # pragma: no cover
                logger.warning("Background indexer sync failed: %s", e)
            finally:
                _clear_queue()
                _release_lease(_connect())

        except Exception as e:  # pragma: no cover
            logger.warning("Indexer loop error: %s", e)
            if _indexer_stop.wait(5.0):
                return


def _clear_queue() -> None:
    try:
        conn = _connect()
        conn.execute("DELETE FROM sync_queue WHERE id = 1")
        conn.commit()
        conn.close()
    except Exception:  # pragma: no cover
        logger.debug("index_worker op failed")


_VAULT_DIR: Path | None = None


def set_vault_dir(vault_dir: Path) -> None:
    """Register the active vault dir so the indexer knows what to sync."""
    global _VAULT_DIR
    _VAULT_DIR = Path(vault_dir).resolve()


def _resolve_vault_dir() -> Path | None:
    import os

    if _VAULT_DIR is not None:
        return _VAULT_DIR
    env = os.getenv("POWER_VAULT_DIR") or os.getenv("POWER_VAULT_PATH")
    if env:
        return Path(env).resolve()
    return None


def get_coverage(vault_dir: Path) -> tuple[int, int]:
    """Return (indexed_files, total_files) for the staleness footer."""
    total = 0
    try:
        for filepath in vault_dir.rglob("*.md"):
            if filepath.name in ("index.md", "log.md", "_index.md"):
                continue
            if should_skip(vault_dir, str(filepath.relative_to(vault_dir))):
                continue
            total += 1
    except Exception:  # pragma: no cover
        logger.debug("index_worker op failed")

    indexed = 0
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM file_metadata")
        indexed = cur.fetchone()[0]
        conn.close()
    except Exception:  # pragma: no cover
        logger.debug("index_worker op failed")

    return indexed, total


def _pid() -> int:
    import os

    return os.getpid()


def _pid_alive(pid: int) -> bool:
    import os

    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True

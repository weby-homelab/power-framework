"""Database initialization helper."""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)


def _init_db(conn: sqlite3.Connection) -> None:
    """Initialize the SQLite database schema."""
    # WAL + busy timeout prevent "database is locked" under parallel embedding.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    # Performance: keep 64MB of page cache in RAM and memory-map the DB file
    # (up to 1GB). Eliminates cold I/O spikes after restart — warm queries stay
    # RAM-bound (sub-100ms p95). See Performance Plan §3.
    conn.execute("PRAGMA cache_size=-65536")
    try:
        conn.execute("PRAGMA mmap_size=1073741824")
    except sqlite3.OperationalError:  # pragma: no cover - platform without mmap
        logger.debug("mmap_size pragma not supported, skipping")
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS fts_notes USING fts5(
            title,
            tags,
            description,
            content,
            rel_path UNINDEXED,
            note_type UNINDEXED,
            tokenize='unicode61'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_metadata (
            rel_path TEXT PRIMARY KEY,
            mtime REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS doc_embeddings (
            rel_path TEXT PRIMARY KEY,
            embedding BLOB,
            mtime REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunk_embeddings (
            chunk_id TEXT PRIMARY KEY,
            rel_path TEXT,
            embedding BLOB,
            content TEXT,
            mtime REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tf_vectors (
            rel_path TEXT PRIMARY KEY,
            tf_data TEXT,
            mtime REAL
        )
    """)
    conn.commit()

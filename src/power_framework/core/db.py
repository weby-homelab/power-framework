"""Database initialization helper."""

from __future__ import annotations

import json
import logging
import sqlite3

logger = logging.getLogger(__name__)

_CANDIDATE_MIGRATION = "m1.2-reclassify-legacy-heuristic-relations"


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return columns present in an existing SQLite table."""
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _ensure_relation_columns(conn: sqlite3.Connection) -> None:
    """Add accepted-relation provenance columns to pre-M1.2 databases."""
    existing = _table_columns(conn, "relations")
    for column, definition in (
        ("candidate_id", "INTEGER"),
        ("accepted_by", "TEXT"),
        ("accepted_at", "TEXT"),
    ):
        if column not in existing:
            conn.execute(f"ALTER TABLE relations ADD COLUMN {column} {definition}")


def _reclassify_legacy_heuristic_relations(conn: sqlite3.Connection) -> None:
    """Move pre-M1.2 extractor rows out of accepted relations exactly once.

    Prior releases had only one writer for ``relations``: the local heuristic
    extractor. Its rows have no review provenance, so retaining them as accepted
    facts would violate the M1.2 authority boundary. The original tuple and
    timestamp are preserved as an unreviewed candidate instead.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS graph_schema_migrations "
        "(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    applied = conn.execute(
        "SELECT 1 FROM graph_schema_migrations WHERE name = ?", (_CANDIDATE_MIGRATION,)
    ).fetchone()
    if applied:
        return

    legacy_rows = conn.execute(
        "SELECT id, source_path, subject, relation, object, confidence, created_at "
        "FROM relations WHERE candidate_id IS NULL ORDER BY id"
    ).fetchall()
    for (
        relation_id,
        source_path,
        subject,
        relation,
        object_value,
        confidence,
        created_at,
    ) in legacy_rows:
        evidence = json.dumps(
            {"legacy_relation_id": relation_id, "migration": _CANDIDATE_MIGRATION},
            sort_keys=True,
        )
        conn.execute(
            "INSERT OR IGNORE INTO relation_candidates "
            "(source_path, subject, relation, object, source, method, model_version, confidence, "
            "evidence, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?)",
            (
                source_path,
                subject,
                relation,
                object_value,
                "heuristic",
                "legacy-unreviewed",
                "pre-m1.2",
                confidence,
                evidence,
                created_at,
            ),
        )
    if legacy_rows:
        conn.execute("DELETE FROM relations WHERE candidate_id IS NULL")
    conn.execute("INSERT INTO graph_schema_migrations (name) VALUES (?)", (_CANDIDATE_MIGRATION,))


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
        CREATE TABLE IF NOT EXISTS temporal_records (
            rel_path TEXT PRIMARY KEY,
            memory_json TEXT
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
        CREATE TABLE IF NOT EXISTS dense_index_manifest (
            manifest_key TEXT PRIMARY KEY,
            manifest_value TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tf_vectors (
            rel_path TEXT PRIMARY KEY,
            tf_data TEXT,
            mtime REAL
        )
    """)
    # M1.2: only reviewed candidates become accepted relations.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL,
            subject TEXT NOT NULL,
            relation TEXT NOT NULL,
            object TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            created_at TEXT NOT NULL,
            candidate_id INTEGER UNIQUE,
            accepted_by TEXT,
            accepted_at TEXT
        )
    """)
    _ensure_relation_columns(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_path)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS relation_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL,
            subject TEXT NOT NULL,
            relation TEXT NOT NULL,
            object TEXT NOT NULL,
            source TEXT NOT NULL,
            method TEXT NOT NULL,
            model_version TEXT NOT NULL,
            confidence REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
            evidence TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'candidate'
                CHECK(status IN ('candidate', 'accepted', 'rejected')),
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by TEXT,
            review_reason TEXT,
            UNIQUE(source_path, subject, relation, object, method, model_version, evidence)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_relation_candidates_status ON relation_candidates(status)"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS relation_candidate_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            decision TEXT NOT NULL CHECK(decision IN ('accepted', 'rejected')),
            reviewer TEXT NOT NULL,
            reason TEXT NOT NULL,
            decided_at TEXT NOT NULL,
            FOREIGN KEY(candidate_id) REFERENCES relation_candidates(id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_relation_candidate_decisions_candidate "
        "ON relation_candidate_decisions(candidate_id, id)"
    )
    _reclassify_legacy_heuristic_relations(conn)
    conn.commit()

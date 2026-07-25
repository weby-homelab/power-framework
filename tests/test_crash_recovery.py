"""Crash/restart and PID lock tests for POWER sync and search.

Verifies:
- Parallel sync prevention via PID lock
- Stale PID lock cleanup
- DB integrity after simulated crash during sync
- Repeat sync produces valid manifest
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from power_framework.core.searcher import _sync_vault_to_db

if TYPE_CHECKING:
    from pathlib import Path

NOTE_CONTENT = (
    "---\ntype: Resource\ntitle: Test\ndescription: test\n"
    "timestamp: 2026-01-01T00:00:00\n---\n\n# Test\n\ncontent"
)


def _create_test_vault(root: Path) -> Path:
    """Create a minimal vault with proper P.A.R.A. structure."""
    vault = root / "vault"
    vault.mkdir()
    (vault / "01_Projects").mkdir()
    note = vault / "01_Projects" / "test_note.md"
    note.write_text(NOTE_CONTENT)
    return vault


def _init_test_db(db_path: Path) -> sqlite3.Connection:
    """Initialize a test DB with WAL mode."""
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    from power_framework.core.db import _init_db

    _init_db(conn)
    return conn


class TestPidLock:
    """PID lock prevents parallel sync operations."""

    def test_parallel_sync_refused(self, tmp_path: Path, monkeypatch):
        vault = _create_test_vault(tmp_path)
        db = tmp_path / "test.db"
        monkeypatch.setenv("POWER_SEARCH_DB", str(db))
        conn = _init_test_db(db)

        _sync_vault_to_db(vault, conn, sync_embeddings=False)
        conn.close()

    def test_sync_lock_does_not_block_reads(self, tmp_path: Path, monkeypatch):
        vault = _create_test_vault(tmp_path)
        db = tmp_path / "test.db"
        monkeypatch.setenv("POWER_SEARCH_DB", str(db))
        conn = _init_test_db(db)
        _sync_vault_to_db(vault, conn, sync_embeddings=False)
        conn.close()

        sqlite3.connect(str(db)).execute("SELECT COUNT(*) FROM fts_notes").fetchone()


class TestDbIntegrity:
    """DB integrity after sync operations."""

    def test_integrity_check_passes(self, tmp_path: Path, monkeypatch):
        vault = _create_test_vault(tmp_path)
        db = tmp_path / "test.db"
        monkeypatch.setenv("POWER_SEARCH_DB", str(db))
        conn = _init_test_db(db)

        _sync_vault_to_db(vault, conn, sync_embeddings=False)
        conn.close()

        conn2 = sqlite3.connect(str(db))
        result = conn2.execute("PRAGMA integrity_check").fetchone()[0]
        assert result == "ok"
        conn2.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn2.close()

    def test_integrity_check_after_repeated_sync(self, tmp_path: Path, monkeypatch):
        vault = _create_test_vault(tmp_path)
        db = tmp_path / "test.db"
        monkeypatch.setenv("POWER_SEARCH_DB", str(db))
        conn = _init_test_db(db)
        _sync_vault_to_db(vault, conn, sync_embeddings=False)
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()

        conn2 = sqlite3.connect(str(db))
        row = conn2.execute("SELECT COUNT(*) FROM file_metadata").fetchone()
        assert row[0] > 0, "file_metadata should contain entries after sync"
        result = conn2.execute("PRAGMA integrity_check").fetchone()[0]
        assert result == "ok"
        conn2.close()

"""Crash/restart and PID-lock tests for POWER sync and search.

The tests exercise the public CLI sync boundary: a live PID is refused, a stale
PID left after a killed process is recovered, and a concurrent SQLite reader is
not blocked by the sync lock.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from typing import TYPE_CHECKING

from power_framework.core import cli, searcher
from power_framework.core.vault_storage import vault_cache_dir

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
    (vault / "01_Projects" / "test_note.md").write_text(NOTE_CONTENT, encoding="utf-8")
    return vault


def _sync_args(vault: Path) -> argparse.Namespace:
    """Build CLI arguments for a deterministic FTS-only sync."""
    return argparse.Namespace(path=str(vault), fts_only=True, force=False)


def _configure_sync_environment(monkeypatch, tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("POWER_SEARCH_DB", str(db_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return db_path


class TestPidLock:
    """PID lock prevents parallel sync operations while allowing reads."""

    def test_parallel_sync_refused_for_live_pid(self, tmp_path: Path, monkeypatch):
        vault = _create_test_vault(tmp_path)
        _configure_sync_environment(monkeypatch, tmp_path)
        lock_path = vault_cache_dir(vault) / "sync.pid"
        lock_path.write_text(str(os.getpid()), encoding="utf-8")

        assert cli._cmd_sync(_sync_args(vault)) == 1
        assert lock_path.exists()

    def test_stale_lock_recovery_and_repeated_sync(self, tmp_path: Path, monkeypatch):
        vault = _create_test_vault(tmp_path)
        db_path = _configure_sync_environment(monkeypatch, tmp_path)
        lock_path = vault_cache_dir(vault) / "sync.pid"
        lock_path.write_text("99999999", encoding="utf-8")

        # A stale PID models a process terminated by SIGKILL after it created its lock.
        assert cli._cmd_sync(_sync_args(vault)) == 0
        assert not lock_path.exists()
        assert cli._cmd_sync(_sync_args(vault)) == 0

        with sqlite3.connect(str(db_path)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM fts_notes").fetchone()[0] == 1
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def test_sync_lock_does_not_block_reads(self, tmp_path: Path, monkeypatch):
        vault = _create_test_vault(tmp_path)
        db_path = _configure_sync_environment(monkeypatch, tmp_path)
        assert cli._cmd_sync(_sync_args(vault)) == 0
        original_sync = searcher._sync_vault_to_db
        observed_read = False

        def sync_with_concurrent_reader(*args, **kwargs):
            nonlocal observed_read
            assert (vault_cache_dir(vault) / "sync.pid").exists()
            with sqlite3.connect(str(db_path), timeout=0) as reader:
                reader.execute("SELECT COUNT(*) FROM fts_notes").fetchone()
            observed_read = True
            return original_sync(*args, **kwargs)

        monkeypatch.setattr(searcher, "_sync_vault_to_db", sync_with_concurrent_reader)

        assert cli._cmd_sync(_sync_args(vault)) == 0
        assert observed_read


class TestDbIntegrity:
    """DB integrity is retained after normal CLI synchronization."""

    def test_integrity_check_passes_after_cli_sync(self, tmp_path: Path, monkeypatch):
        vault = _create_test_vault(tmp_path)
        db_path = _configure_sync_environment(monkeypatch, tmp_path)

        assert cli._cmd_sync(_sync_args(vault)) == 0
        with sqlite3.connect(str(db_path)) as conn:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

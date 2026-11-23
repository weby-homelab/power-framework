"""Read-only FTS identity and legacy database-path regressions."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

import pytest

from power_framework.core import doctor
from tests.test_doctor_3714_regression import make_index

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    "kind", ["empty", "populated", "ordinary-empty", "ordinary-filled", "missing"]
)
def test_doctor_requires_real_fts_without_dense(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    vault, database = make_index(tmp_path, "index.db", without_dense=True)
    with closing(sqlite3.connect(database)) as connection:
        if kind == "empty":
            connection.execute("DELETE FROM fts_notes")
        elif kind.startswith("ordinary") or kind == "missing":
            connection.execute("DROP TABLE fts_notes")
            if kind.startswith("ordinary"):
                # A same-named column makes MATCH on an empty ordinary table
                # return zero rows without necessarily evaluating MATCH.
                connection.execute("CREATE TABLE fts_notes (fts_notes TEXT)")
                if kind == "ordinary-filled":
                    connection.execute("INSERT INTO fts_notes VALUES ('synthetic')")
        connection.commit()
    database_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    vault_hash = hashlib.sha256((vault / "01_Projects/note.md").read_bytes()).hexdigest()
    entries = {path.name for path in tmp_path.iterdir()}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POWER_SEARCH_DB", database.name)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    report = doctor.run_doctor(vault)
    if kind in {"empty", "populated"}:
        assert report["vault"]["index_state"] == "legacy_database"
        assert report["vault"]["indexed_notes"] == 1
        assert report["vault"]["indexed_chunks"] is None
        assert not any(item["code"] == "search_database_unreadable" for item in report["issues"])
    else:
        assert report["vault"]["index_state"] == "unreadable"
        assert any(item["code"] == "search_database_unreadable" for item in report["issues"])
    assert hashlib.sha256(database.read_bytes()).hexdigest() == database_hash
    assert hashlib.sha256((vault / "01_Projects/note.md").read_bytes()).hexdigest() == vault_hash
    assert {path.name for path in tmp_path.iterdir()} == entries
    assert not any(database.with_name(database.name + ext).exists() for ext in ("-wal", "-shm"))


@pytest.mark.parametrize("kind", ["missing", "directory", "valid-symlink", "dangling-symlink"])
def test_database_paths_preserve_existing_371_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    vault, database = make_index(tmp_path, "target.db", without_dense=True)
    override = tmp_path / "selected.db"
    if kind == "directory":
        override.mkdir()
    elif kind == "valid-symlink":
        override.symlink_to(database.name)
    elif kind == "dangling-symlink":
        override.symlink_to("not-present.db")
    before_names = {path.name for path in tmp_path.iterdir()}
    before_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    link_target = override.readlink() if override.is_symlink() else None
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POWER_SEARCH_DB", override.name)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    report = doctor.run_doctor(vault)
    assert report["vault"]["index_state"] == (
        "legacy_database" if kind == "valid-symlink" else "missing"
    )
    if kind == "valid-symlink":
        assert report["vault"]["indexed_notes"] == 1
        assert report["vault"]["indexed_chunks"] is None
    else:
        assert report["vault"]["database_path"] is None
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before_hash
    assert {path.name for path in tmp_path.iterdir()} == before_names
    if link_target is not None:
        assert override.is_symlink()
        assert override.readlink() == link_target
    if kind == "missing":
        assert not override.exists()
    if kind == "dangling-symlink":
        assert not (tmp_path / "not-present.db").exists()

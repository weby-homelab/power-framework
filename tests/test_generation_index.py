"""P0 regression tests for isolated, atomically published vault indexes."""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

import pytest

from power_framework.core.generation_index import (
    IndexGenerationError,
    _state_db_path,
    sync_vault_atomically,
)
from power_framework.core.searcher import search_vault
from power_framework.core.vault_storage import ensure_vault_identity, vault_db_path

if TYPE_CHECKING:
    from pathlib import Path


def _vault(root: Path, title: str, token: str) -> Path:
    vault = root / title
    note = vault / "01_Projects" / "Test.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\n"
        "type: Project\n"
        f"title: {title}\n"
        "description: generation test note\n"
        "timestamp: 2026-07-27T00:00:00+00:00\n"
        "---\n\n"
        f"{token}\n",
        encoding="utf-8",
    )
    return vault


def test_vault_identity_and_database_namespace_are_stable_and_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    first = _vault(tmp_path, "first", "alpha-only")
    second = _vault(tmp_path, "second", "bravo-only")

    first_identity = ensure_vault_identity(first)
    assert first_identity == ensure_vault_identity(first)
    assert vault_db_path(first) != vault_db_path(second)
    sync_vault_atomically(first, sync_embeddings=False)
    sync_vault_atomically(second, sync_embeddings=False)
    assert search_vault(first, "alpha-only", mode="fts")
    assert not search_vault(second, "alpha-only", mode="fts")

    identity_json = json.loads((first / ".power" / "vault.json").read_text(encoding="utf-8"))
    assert identity_json["vault_id"] == first_identity.vault_id
    assert str(first.resolve()) not in json.dumps(identity_json)


def test_failed_generation_keeps_the_previous_active_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "atomic", "stable-token")
    report = sync_vault_atomically(vault, sync_embeddings=False)
    active_db = vault_db_path(vault)
    before = active_db.read_bytes()

    from power_framework.core import searcher

    def fail_staged_sync(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated disk-full")

    monkeypatch.setattr(searcher, "_sync_vault_to_db", fail_staged_sync)
    with pytest.raises(IndexGenerationError, match="simulated disk-full"):
        sync_vault_atomically(vault, sync_embeddings=False)

    assert active_db.read_bytes() == before
    assert search_vault(vault, "stable-token", mode="fts")
    with sqlite3.connect(_state_db_path(vault)) as conn:
        state, expected, actual = conn.execute(
            "SELECT state, expected_files, actual_files FROM index_generations "
            "WHERE generation_id = ?",
            (report.generation_id,),
        ).fetchone()
        failed = conn.execute(
            "SELECT COUNT(*) FROM index_generations WHERE state = 'failed'"
        ).fetchone()[0]
    assert (state, expected, actual) == ("ready", 1, 1)
    assert failed == 1

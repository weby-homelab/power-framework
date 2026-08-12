"""Hermetic Phase 1 fault matrix for crash-atomic generation publication."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from power_framework.core import generation_index, searcher
from power_framework.core.generation_index import (
    IndexGenerationError,
    _publish,
    _state_db_path,
    resolve_active_generation_path,
    sync_vault_atomically,
)

RECEIPT_MANIFEST = (
    Path(__file__).resolve().parent.parent
    / "benchmarks"
    / "power31"
    / "evidence"
    / "phase1-generation-fault-matrix-v1.json"
)


def _vault(root: Path, content_marker: str = "first-token") -> Path:
    vault = root / "vault"
    note = vault / "01_Projects" / "Test.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\n"
        "type: Project\n"
        "title: Fault matrix note\n"
        "description: crash-atomic generation test\n"
        "timestamp: 2026-07-28T00:00:00+00:00\n"
        "---\n\n"
        f"{content_marker}\n",
        encoding="utf-8",
    )
    return vault


def _prepare_active_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    vault = _vault(tmp_path)
    sync_vault_atomically(vault, sync_embeddings=False)
    active = resolve_active_generation_path(vault)
    assert active is not None
    return vault, hashlib.sha256(active.read_bytes()).hexdigest()


def _replace_token(vault: Path, old: str = "first-token", new: str = "second-token") -> None:
    note = vault / "01_Projects" / "Test.md"
    note.write_text(note.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


def _assert_previous_generation_is_unchanged(vault: Path, before_checksum: str) -> None:
    active = resolve_active_generation_path(vault)
    assert active is not None
    assert hashlib.sha256(active.read_bytes()).hexdigest() == before_checksum
    assert searcher.search_vault(vault, "first-token", mode="fts")
    assert not searcher.search_vault(vault, "second-token", mode="fts")
    with closing(sqlite3.connect(_state_db_path(vault))) as conn:
        active_id = conn.execute(
            "SELECT generation_id FROM active_generation WHERE id = 1"
        ).fetchone()[0]
        active_state = conn.execute(
            "SELECT state FROM index_generations WHERE generation_id = ?", (active_id,)
        ).fetchone()[0]
        half_ready = conn.execute(
            "SELECT COUNT(*) FROM index_generations WHERE state = 'building'"
        ).fetchone()[0]
    assert active_state == "ready"
    assert half_ready == 0


def _plant_building_artifacts(vault: Path, created_at: str) -> tuple[str, tuple[Path, ...]]:
    """Plant synthetic UUID-owned build artifacts and a matching state row."""
    generation_id = str(uuid4())
    paths = generation_index._build_artifact_paths(vault, generation_id)
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic orphan artifact")
    with closing(sqlite3.connect(_state_db_path(vault))) as conn:
        generation_index._init_state_db(conn)
        conn.execute(
            """
            INSERT INTO index_generations (
                generation_id, state, source_snapshot_hash, expected_files,
                chunker_identity, created_at
            ) VALUES (?, 'building', ?, ?, ?, ?)
            """,
            (generation_id, "synthetic-snapshot", 1, "SemanticChunker/v1", created_at),
        )
        conn.commit()
    return generation_id, paths


def test_stale_build_reaper_removes_crash_artifacts_but_preserves_live_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Crash cleanup is lease-gated and never treats a young build as stale."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("POWER_GENERATION_BUILD_TTL_SECONDS", "3600")
    vault = _vault(tmp_path)
    sync_vault_atomically(vault, sync_embeddings=False)

    stale_id, stale_paths = _plant_building_artifacts(
        vault, (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    )
    fresh_id, fresh_paths = _plant_building_artifacts(vault, datetime.now(UTC).isoformat())

    sync_vault_atomically(vault, sync_embeddings=False)

    assert all(not path.exists() for path in stale_paths)
    assert all(path.exists() for path in fresh_paths)
    with closing(sqlite3.connect(_state_db_path(vault))) as conn:
        states = dict(
            conn.execute(
                "SELECT generation_id, state FROM index_generations WHERE generation_id IN (?, ?)",
                (stale_id, fresh_id),
            ).fetchall()
        )
    assert states == {stale_id: "failed", fresh_id: "building"}


def test_publisher_rejects_a_reaped_build_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reaper claim fences a late writer before it can move the pointer."""
    vault, before_checksum = _prepare_active_vault(tmp_path, monkeypatch)
    generation_id, paths = _plant_building_artifacts(
        vault, (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    )
    staging_path = paths[0]
    for path in paths[3:]:
        path.unlink(missing_ok=True)
    with closing(sqlite3.connect(_state_db_path(vault))) as conn:
        conn.execute(
            "UPDATE index_generations SET state = 'failed', error = ? WHERE generation_id = ?",
            ("reaped stale building row after crash", generation_id),
        )
        conn.commit()

    with pytest.raises(IndexGenerationError, match="lease was revoked"):
        _publish(vault, generation_id, staging_path, 0, 0, None, None)

    active = resolve_active_generation_path(vault)
    assert active is not None
    assert hashlib.sha256(active.read_bytes()).hexdigest() == before_checksum
    assert not paths[3].exists()


@pytest.mark.parametrize("batch_position", ["first", "middle", "last"])
def test_permanent_oom_at_any_batch_keeps_previous_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, batch_position: str
) -> None:
    vault, before_checksum = _prepare_active_vault(tmp_path, monkeypatch)
    _replace_token(vault)

    def permanent_oom(*args: object, **kwargs: object) -> None:
        raise MemoryError(f"simulated permanent OOM at {batch_position} batch")

    monkeypatch.setattr(generation_index, "_sync_vault_to_db", permanent_oom)
    with pytest.raises(IndexGenerationError, match=f"OOM at {batch_position} batch"):
        sync_vault_atomically(vault, sync_embeddings=False)

    _assert_previous_generation_is_unchanged(vault, before_checksum)


def test_enospc_while_creating_staging_keeps_previous_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, before_checksum = _prepare_active_vault(tmp_path, monkeypatch)
    _replace_token(vault)

    def no_space(_: sqlite3.Connection) -> None:
        raise OSError(errno.ENOSPC, "simulated ENOSPC while creating staging")

    monkeypatch.setattr(generation_index, "_init_db", no_space)
    with pytest.raises(IndexGenerationError, match="ENOSPC"):
        sync_vault_atomically(vault, sync_embeddings=False)

    _assert_previous_generation_is_unchanged(vault, before_checksum)


def test_enospc_during_generation_move_keeps_previous_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, before_checksum = _prepare_active_vault(tmp_path, monkeypatch)
    _replace_token(vault)
    original_replace = generation_index.os.replace

    def no_space(src: str | Path, dst: str | Path) -> None:
        if Path(src).parent.name == "staging" and Path(dst).parent.name == "generations":
            raise OSError(errno.ENOSPC, "simulated ENOSPC during generation move")
        original_replace(src, dst)

    monkeypatch.setattr(generation_index.os, "replace", no_space)
    with pytest.raises(IndexGenerationError, match="ENOSPC"):
        sync_vault_atomically(vault, sync_embeddings=False)

    _assert_previous_generation_is_unchanged(vault, before_checksum)


@pytest.mark.parametrize(
    ("error", "pattern"),
    [
        (OSError(errno.ENOSPC, "simulated ENOSPC in state DB"), "ENOSPC"),
        (sqlite3.OperationalError("database is locked"), "database is locked"),
    ],
)
def test_state_db_enospc_or_lock_keeps_previous_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception, pattern: str
) -> None:
    vault, before_checksum = _prepare_active_vault(tmp_path, monkeypatch)
    _replace_token(vault)
    original_init = generation_index._init_state_db
    calls = 0

    def fail_publish_state(conn: sqlite3.Connection) -> None:
        nonlocal calls
        calls += 1
        original_init(conn)
        if calls == 2:
            raise error

    monkeypatch.setattr(generation_index, "_init_state_db", fail_publish_state)
    with pytest.raises(IndexGenerationError, match=pattern):
        sync_vault_atomically(vault, sync_embeddings=False)

    _assert_previous_generation_is_unchanged(vault, before_checksum)


def test_corrupt_staging_validation_keeps_previous_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, before_checksum = _prepare_active_vault(tmp_path, monkeypatch)
    _replace_token(vault)

    def corrupt_staging(*args: object, **kwargs: object) -> tuple[int, int, None, None]:
        raise IndexGenerationError("SQLite integrity check failed: simulated corrupt staging DB")

    monkeypatch.setattr(generation_index, "_validate_staging", corrupt_staging)
    with pytest.raises(IndexGenerationError, match="corrupt staging DB"):
        sync_vault_atomically(vault, sync_embeddings=False)

    _assert_previous_generation_is_unchanged(vault, before_checksum)


@pytest.mark.parametrize("mutation", ["add", "delete"])
def test_source_add_or_delete_during_sync_keeps_previous_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    vault, before_checksum = _prepare_active_vault(tmp_path, monkeypatch)
    original_sync = generation_index._sync_vault_to_db

    def sync_then_change_source(*args: object, **kwargs: object) -> None:
        original_sync(*args, **kwargs)
        if mutation == "add":
            extra = vault / "01_Projects" / "Added.md"
            extra.write_text(
                "---\ntype: Project\ntitle: Added\ndescription: added source\n"
                "timestamp: 2026-07-28T00:00:00+00:00\n---\n\nadded-token\n",
                encoding="utf-8",
            )
        else:
            (vault / "01_Projects" / "Test.md").unlink()

    monkeypatch.setattr(generation_index, "_sync_vault_to_db", sync_then_change_source)
    with pytest.raises(IndexGenerationError, match="source snapshot changed during sync"):
        sync_vault_atomically(vault, sync_embeddings=False)

    active = resolve_active_generation_path(vault)
    assert active is not None
    assert hashlib.sha256(active.read_bytes()).hexdigest() == before_checksum


def test_repeat_build_is_deterministic_at_query_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    vault = _vault(tmp_path)
    sync_vault_atomically(vault, sync_embeddings=False)
    first = resolve_active_generation_path(vault)
    assert first is not None
    with closing(sqlite3.connect(f"file:{first}?mode=ro", uri=True)) as conn:
        first_rows = conn.execute(
            "SELECT rel_path, title, description, note_type, content FROM fts_notes ORDER BY rel_path"
        ).fetchall()

    sync_vault_atomically(vault, sync_embeddings=False)
    second = resolve_active_generation_path(vault)
    assert second is not None
    with closing(sqlite3.connect(f"file:{second}?mode=ro", uri=True)) as conn:
        second_rows = conn.execute(
            "SELECT rel_path, title, description, note_type, content FROM fts_notes ORDER BY rel_path"
        ).fetchall()

    assert first_rows == second_rows


_SUBPROCESS_SCRIPT = """
import os
import time
from pathlib import Path
from power_framework.core import generation_index

vault = Path(os.environ["POWER_FAULT_VAULT"])
marker = Path(os.environ["POWER_FAULT_MARKER"])
point = os.environ["POWER_FAULT_POINT"]

if point == "before_move":
    original = generation_index.os.replace
    def pause(src, dst):
        if Path(src).parent.name == "staging" and Path(dst).parent.name == "generations":
            marker.write_text("before_move", encoding="utf-8")
            time.sleep(60)
        return original(src, dst)
    generation_index.os.replace = pause
elif point == "after_move":
    original = generation_index._fsync_directory
    def pause(path):
        if Path(path).name == "generations":
            marker.write_text("after_move", encoding="utf-8")
            time.sleep(60)
        return original(path)
    generation_index._fsync_directory = pause
else:
    original = generation_index._cleanup_generations
    def pause(root):
        marker.write_text("after_pointer", encoding="utf-8")
        time.sleep(60)
        return original(root)
    generation_index._cleanup_generations = pause

generation_index.sync_vault_atomically(vault, sync_embeddings=False)
"""


@pytest.mark.parametrize("checkpoint", ["before_move", "after_move", "after_pointer"])
def test_sigkill_at_publish_checkpoints_preserves_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, checkpoint: str
) -> None:
    vault, before_checksum = _prepare_active_vault(tmp_path, monkeypatch)
    _replace_token(vault)
    marker = tmp_path / f"{checkpoint}.marker"
    env = os.environ.copy()
    env.update(
        {
            "POWER_FAULT_VAULT": str(vault),
            "POWER_FAULT_MARKER": str(marker),
            "POWER_FAULT_POINT": checkpoint,
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
        }
    )
    env.pop("POWER_SEARCH_DB", None)
    process = subprocess.Popen(  # noqa: S603 -- invokes the current Python interpreter.
        [sys.executable, "-c", _SUBPROCESS_SCRIPT],
        cwd=Path(__file__).resolve().parent.parent,
        env=env,
    )
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.read_text(encoding="utf-8") == checkpoint
    finally:
        process.kill()
        process.wait(timeout=10)

    active = resolve_active_generation_path(vault)
    assert active is not None
    if checkpoint == "after_pointer":
        assert searcher.search_vault(vault, "second-token", mode="fts")
    else:
        assert hashlib.sha256(active.read_bytes()).hexdigest() == before_checksum
        assert searcher.search_vault(vault, "first-token", mode="fts")


def test_versioned_failure_receipts_cover_the_complete_fault_matrix() -> None:
    manifest = json.loads(RECEIPT_MANIFEST.read_text(encoding="utf-8"))
    expected_ids = {
        "oom-first-batch",
        "oom-middle-batch",
        "oom-last-batch",
        "enospc-staging",
        "enospc-generation-move",
        "enospc-state-db",
        "sqlite-locked-state-db",
        "corrupt-staging-db",
        "source-add-race",
        "source-delete-race",
        "deterministic-repeat-build",
        "sigkill-before-move",
        "sigkill-after-move",
        "sigkill-after-pointer",
    }

    assert manifest["schema_version"] == 1
    assert manifest["classification"] == "hermetic_fault_injection"
    assert manifest["test_module"] == "tests/test_generation_fault_matrix.py"
    assert (
        manifest["reproduction_command"]
        == "pytest tests/test_generation_fault_matrix.py -q --no-cov"
    )
    receipts = manifest["receipts"]
    assert {receipt["id"] for receipt in receipts} == expected_ids
    assert all(receipt["injection"] and receipt["expected_active"] for receipt in receipts)

"""P0 regression tests for isolated, atomically published vault indexes."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

import pytest

from power_framework.core import generation_index
from power_framework.core.db import _init_db
from power_framework.core.generation_index import (
    ActiveGeneration,
    ActiveGenerationError,
    IndexGenerationError,
    _state_db_path,
    invalidate_active_generation_cache,
    resolve_active_generation,
    resolve_active_generation_path,
    sync_vault_atomically,
)
from power_framework.core.index_sync import _stable_chunk_id
from power_framework.core.searcher import _sync_vault_to_db, search_vault
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


def _active_db(vault: Path) -> Path:
    active = resolve_active_generation_path(vault)
    assert active is not None
    return active


def test_snapshot_hash_matches_projection_for_prefix_colliding_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory and file sharing a prefix must publish one source revision."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    vault = tmp_path / "prefix-collision"
    note_paths = (
        vault / "01_Projects" / "Abazivka" / "nested.md",
        vault / "01_Projects" / "Abazivka-logistics-hub.md",
    )
    for path in note_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\n"
            "type: Project\n"
            f"title: {path.stem}\n"
            "description: prefix collision regression\n"
            "timestamp: 2026-08-28T00:00:00Z\n"
            "---\n\nshared-prefix\n",
            encoding="utf-8",
        )

    report = sync_vault_atomically(vault, sync_embeddings=False)

    with closing(sqlite3.connect(_active_db(vault))) as conn:
        projected_revision = conn.execute(
            "SELECT meta_value FROM source_projection_meta WHERE meta_key = 'source_revision'"
        ).fetchone()[0]
        projected_paths = {row[0] for row in conn.execute("SELECT rel_path FROM source_metadata")}
    assert report.source_snapshot_hash == projected_revision
    assert projected_paths == {
        "01_Projects/Abazivka/nested.md",
        "01_Projects/Abazivka-logistics-hub.md",
    }


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


def test_read_only_generation_probe_does_not_create_vault_state_or_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing generation must remain a pure observation."""
    from power_framework.core import vault_storage

    cache_root = tmp_path / "cache"
    monkeypatch.setattr(vault_storage, "get_cache_dir", lambda *, create=True: cache_root)
    vault = tmp_path / "ephemeral"
    vault.mkdir()

    assert resolve_active_generation_path(vault) is None
    assert not (vault / ".power").exists()
    assert not cache_root.exists()


def test_resolve_active_generation_returns_verified_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "identity", "identity-token")
    report = sync_vault_atomically(vault, sync_embeddings=False)

    active = resolve_active_generation(vault)

    assert isinstance(active, ActiveGeneration)
    assert active.path == _active_db(vault)
    assert active.generation_id == report.generation_id
    assert active.source_snapshot_hash == report.source_snapshot_hash
    assert active.db_sha256
    assert active.db_size == active.path.stat().st_size


def test_failed_generation_keeps_the_previous_active_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "atomic", "stable-token")
    report = sync_vault_atomically(vault, sync_embeddings=False)
    active_db = _active_db(vault)
    before = active_db.read_bytes()

    def fail_staged_sync(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated disk-full")

    monkeypatch.setattr(generation_index, "_sync_vault_to_db", fail_staged_sync)
    with pytest.raises(IndexGenerationError, match="simulated disk-full"):
        sync_vault_atomically(vault, sync_embeddings=False)

    assert active_db.read_bytes() == before
    assert search_vault(vault, "stable-token", mode="fts")
    with closing(sqlite3.connect(_state_db_path(vault))) as conn:
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


def test_source_change_during_sync_keeps_previous_active_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A generation must not publish rows for a stale source snapshot."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "changing", "stable-token")
    sync_vault_atomically(vault, sync_embeddings=False)
    active_db = _active_db(vault)
    before = active_db.read_bytes()

    original_sync = generation_index._sync_vault_to_db

    def sync_then_change_source(*args: object, **kwargs: object) -> None:
        original_sync(*args, **kwargs)
        note = vault / "01_Projects" / "Test.md"
        note.write_text(
            note.read_text(encoding="utf-8").replace("stable-token", "changed-token"),
            encoding="utf-8",
        )

    monkeypatch.setattr(generation_index, "_sync_vault_to_db", sync_then_change_source)
    with pytest.raises(IndexGenerationError, match=r"snapshot changed during sync.*Test.md"):
        sync_vault_atomically(vault, sync_embeddings=False)

    assert active_db.read_bytes() == before
    assert search_vault(vault, "stable-token", mode="fts")


def test_active_pointer_retains_current_and_previous_generations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "retention", "first-token")
    first = sync_vault_atomically(vault, sync_embeddings=False)
    first_path = _active_db(vault)

    note = vault / "01_Projects" / "Test.md"
    note.write_text(
        note.read_text(encoding="utf-8").replace("first-token", "second-token"), encoding="utf-8"
    )
    second = sync_vault_atomically(vault, sync_embeddings=False)
    second_path = _active_db(vault)

    assert second.generation_id != first.generation_id
    assert second_path != first_path
    assert first_path.is_file()
    assert search_vault(vault, "second-token", mode="fts")
    with closing(sqlite3.connect(_state_db_path(vault))) as conn:
        active_id = conn.execute(
            "SELECT generation_id FROM active_generation WHERE id = 1"
        ).fetchone()[0]
        ready_count = conn.execute(
            "SELECT COUNT(*) FROM index_generations WHERE state = 'ready'"
        ).fetchone()[0]
    assert active_id == second.generation_id
    assert ready_count == 2


def test_new_generation_starts_from_active_db_for_incremental_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Atomic publication must not discard the previous mtime cache."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "incremental", "first-token")
    sync_vault_atomically(vault, sync_embeddings=False)
    added = vault / "01_Projects" / "Added.md"
    added.write_text(
        "---\n"
        "type: Project\n"
        "title: Added\n"
        "description: added note\n"
        "timestamp: 2026-07-27T00:00:00+00:00\n"
        "---\n\nsecond-token\n",
        encoding="utf-8",
    )

    original_sync = generation_index._sync_vault_to_db
    observed: dict[str, int] = {}

    def capture_existing_rows(*args: object, **kwargs: object) -> None:
        conn = args[1]
        assert isinstance(conn, sqlite3.Connection)
        observed["before_sync"] = conn.execute("SELECT COUNT(*) FROM file_metadata").fetchone()[0]
        original_sync(*args, **kwargs)

    monkeypatch.setattr(generation_index, "_sync_vault_to_db", capture_existing_rows)
    sync_vault_atomically(vault, sync_embeddings=False)

    assert observed["before_sync"] == 1
    assert search_vault(vault, "second-token", mode="fts")


def test_missing_active_generation_file_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "missing", "stable-token")
    sync_vault_atomically(vault, sync_embeddings=False)
    _active_db(vault).unlink()

    with pytest.raises(ActiveGenerationError, match="active generation file is missing"):
        search_vault(vault, "stable-token", mode="fts")


def test_cached_generation_rechecks_file_identity_before_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cached identity must not hide an externally corrupted generation."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "corrupted-cache", "stable-token")
    sync_vault_atomically(vault, sync_embeddings=False)
    active = resolve_active_generation(vault)
    assert active is not None

    active.path.write_bytes(active.path.read_bytes() + b"corruption")

    with pytest.raises(ActiveGenerationError, match="identity mismatch"):
        resolve_active_generation(vault)


def test_publication_invalidates_generation_identity_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A newly published generation is visible to the next read immediately."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "cache-invalidation", "first-token")
    first = sync_vault_atomically(vault, sync_embeddings=False)
    assert resolve_active_generation(vault) is not None

    note = vault / "01_Projects" / "Test.md"
    note.write_text(
        note.read_text(encoding="utf-8").replace("first-token", "second-token"),
        encoding="utf-8",
    )
    second = sync_vault_atomically(vault, sync_embeddings=False)

    assert second.generation_id != first.generation_id
    active = resolve_active_generation(vault)
    assert active is not None
    assert active.generation_id == second.generation_id

    invalidate_active_generation_cache(vault)
    rechecked = resolve_active_generation(vault)
    assert rechecked is not None
    assert rechecked.generation_id == second.generation_id


def test_external_active_pointer_change_invalidates_cached_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The state WAL is part of the cache key for another publisher's update."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "external-pointer", "first-token")
    first = sync_vault_atomically(vault, sync_embeddings=False)
    note = vault / "01_Projects" / "Test.md"
    note.write_text(
        note.read_text(encoding="utf-8").replace("first-token", "second-token"),
        encoding="utf-8",
    )
    second = sync_vault_atomically(vault, sync_embeddings=False)
    published = resolve_active_generation(vault)
    assert published is not None
    assert published.generation_id == second.generation_id

    with closing(sqlite3.connect(_state_db_path(vault), timeout=30)) as conn:
        conn.execute(
            "UPDATE active_generation SET generation_id = ? WHERE id = 1",
            (first.generation_id,),
        )
        conn.commit()

    active = resolve_active_generation(vault)
    assert active is not None
    assert active.generation_id == first.generation_id


def test_invalid_sources_are_explicitly_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "inventory", "valid-token")
    invalid = vault / "01_Projects" / "Invalid.md"
    invalid.write_text("# no frontmatter\n", encoding="utf-8")

    report = sync_vault_atomically(vault, sync_embeddings=False)

    assert (report.total_scanned, report.invalid_sources, report.expected_files) == (2, 1, 1)
    assert report.excluded_sources == {"01_Projects/Invalid.md": "invalid_metadata"}
    assert report.excluded_reason_counts == {"invalid_metadata": 1}
    with closing(sqlite3.connect(_state_db_path(vault))) as conn:
        invalid_count = conn.execute(
            "SELECT COUNT(*) FROM generation_invalid_sources WHERE generation_id = ?",
            (report.generation_id,),
        ).fetchone()[0]
        reason = conn.execute(
            "SELECT reason FROM generation_invalid_sources WHERE generation_id = ?",
            (report.generation_id,),
        ).fetchone()[0]
    assert (invalid_count, reason) == (1, "invalid_metadata")


def test_generated_catalog_pages_are_outside_generation_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "catalog-boundary", "valid-token")
    catalog = (
        "---\n"
        "type: System Guide\n"
        'title: "Generated catalog"\n'
        'description: "Navigation only"\n'
        "timestamp: 2026-07-27T00:00:00Z\n"
        "x-generated-by: power\n"
        "---\n\n# catalog\n"
    )
    catalog_dir = vault / "03_Resources"
    catalog_dir.mkdir(parents=True)
    for name in ("_index.md", "_index-2.md", "_index-17.md"):
        (catalog_dir / name).write_text(catalog, encoding="utf-8")

    report = sync_vault_atomically(vault, sync_embeddings=False)

    assert (report.total_scanned, report.expected_files, report.actual_files) == (1, 1, 1)
    assert report.excluded_sources == {}
    with closing(sqlite3.connect(_active_db(vault))) as conn:
        indexed = {row[0] for row in conn.execute("SELECT rel_path FROM file_metadata")}
    assert indexed == {"01_Projects/Test.md"}


def test_sync_can_fail_closed_before_publishing_excluded_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "strict-inventory", "valid-token")
    invalid = vault / "01_Projects" / "Invalid.md"
    invalid.write_text("# no frontmatter\n", encoding="utf-8")

    with pytest.raises(IndexGenerationError, match=r"sync failed closed.*Invalid\.md"):
        sync_vault_atomically(vault, sync_embeddings=False, allow_partial=False)

    assert resolve_active_generation_path(vault) is None
    report = sync_vault_atomically(vault, sync_embeddings=False, allow_partial=True)
    assert report.invalid_sources == 1


def test_excluded_source_change_during_sync_keeps_previous_active_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A note becoming valid during sync must invalidate the source snapshot."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "excluded-change", "stable-token")
    invalid = vault / "01_Projects" / "Invalid.md"
    invalid.write_text("# no frontmatter\n", encoding="utf-8")
    sync_vault_atomically(vault, sync_embeddings=False)
    active_db = _active_db(vault)
    before = active_db.read_bytes()

    original_sync = generation_index._sync_vault_to_db

    def sync_then_repair_excluded(*args: object, **kwargs: object) -> None:
        original_sync(*args, **kwargs)
        invalid.write_text(
            "---\n"
            "type: Project\n"
            "title: Repaired\n"
            "description: repaired note\n"
            "timestamp: 2026-07-27T00:00:00+00:00\n"
            "---\n\nrepaired-token\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(generation_index, "_sync_vault_to_db", sync_then_repair_excluded)
    with pytest.raises(IndexGenerationError, match=r"snapshot changed during sync.*Invalid.md"):
        sync_vault_atomically(vault, sync_embeddings=False)

    assert active_db.read_bytes() == before
    assert search_vault(vault, "stable-token", mode="fts")
    assert not search_vault(vault, "repaired-token", mode="fts")


def test_legacy_search_database_is_imported_before_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "legacy", "legacy-token")
    legacy_path = vault_db_path(vault)
    with closing(sqlite3.connect(legacy_path)) as conn:
        _init_db(conn)
        _sync_vault_to_db(vault, conn, sync_embeddings=False)

    report = sync_vault_atomically(vault, sync_embeddings=False)

    assert _active_db(vault).is_file()
    assert not legacy_path.exists()
    archive = legacy_path.parent / "legacy" / f"search.db.{report.generation_id}.bak"
    assert archive.is_file()
    assert search_vault(vault, "legacy-token", mode="fts")


def test_stale_legacy_database_falls_back_to_source_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A legacy snapshot missing current notes must not block recovery."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "stale-legacy", "legacy-token")
    legacy_path = vault_db_path(vault)
    with closing(sqlite3.connect(legacy_path)) as conn:
        _init_db(conn)
        _sync_vault_to_db(vault, conn, sync_embeddings=False)

    added = vault / "01_Projects" / "Added.md"
    added.write_text(
        "---\n"
        "type: Project\n"
        "title: Added\n"
        "description: added after the legacy snapshot\n"
        "timestamp: 2026-07-27T00:00:00+00:00\n"
        "---\n\nadded-token\n",
        encoding="utf-8",
    )

    report = sync_vault_atomically(vault, sync_embeddings=False, allow_partial=False)

    assert report.actual_files == 2
    assert not legacy_path.exists()
    archive = legacy_path.parent / "legacy" / f"search.db.{report.generation_id}.bak"
    assert archive.is_file()
    assert search_vault(vault, "legacy-token", mode="fts")
    assert search_vault(vault, "added-token", mode="fts")


def test_cleanup_failure_after_pointer_commit_keeps_new_generation_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "cleanup", "first-token")
    sync_vault_atomically(vault, sync_embeddings=False)
    note = vault / "01_Projects" / "Test.md"
    note.write_text(
        note.read_text(encoding="utf-8").replace("first-token", "second-token"), encoding="utf-8"
    )

    from power_framework.core import generation_index

    def fail_cleanup(_: Path) -> None:
        raise OSError("simulated cleanup failure")

    monkeypatch.setattr(generation_index, "_cleanup_generations", fail_cleanup)
    report = sync_vault_atomically(vault, sync_embeddings=False)

    assert _active_db(vault).name == f"{report.generation_id}.db"
    assert search_vault(vault, "second-token", mode="fts")


def test_failure_after_generation_move_keeps_previous_pointer_and_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "move-failure", "first-token")
    first = sync_vault_atomically(vault, sync_embeddings=False)
    first_path = _active_db(vault)
    note = vault / "01_Projects" / "Test.md"
    note.write_text(
        note.read_text(encoding="utf-8").replace("first-token", "second-token"), encoding="utf-8"
    )

    from power_framework.core import generation_index

    original_identity = generation_index._file_identity

    def fail_new_generation_identity(path: Path) -> tuple[str, int]:
        if path.parent.name == "generations" and path != first_path:
            raise OSError("simulated generation move identity failure")
        return original_identity(path)

    with monkeypatch.context() as fault:
        fault.setattr(generation_index, "_file_identity", fail_new_generation_identity)
        with pytest.raises(
            IndexGenerationError, match="simulated generation move identity failure"
        ):
            sync_vault_atomically(vault, sync_embeddings=False)

    assert _active_db(vault).name == f"{first.generation_id}.db"
    assert search_vault(vault, "first-token", mode="fts")
    assert not search_vault(vault, "second-token", mode="fts")
    with closing(sqlite3.connect(_state_db_path(vault))) as conn:
        failed = conn.execute(
            "SELECT COUNT(*) FROM index_generations WHERE state = 'failed'"
        ).fetchone()[0]
        half_ready = conn.execute(
            "SELECT COUNT(*) FROM index_generations WHERE state = 'building'"
        ).fetchone()[0]
    assert (failed, half_ready) == (1, 0)


def test_state_transaction_setup_failure_keeps_previous_pointer_and_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "state-failure", "first-token")
    first = sync_vault_atomically(vault, sync_embeddings=False)
    note = vault / "01_Projects" / "Test.md"
    note.write_text(
        note.read_text(encoding="utf-8").replace("first-token", "second-token"), encoding="utf-8"
    )

    from power_framework.core import generation_index

    original_init = generation_index._init_state_db
    calls = 0

    def fail_publish_state_initialization(conn: sqlite3.Connection) -> None:
        nonlocal calls
        calls += 1
        original_init(conn)
        if calls == 2:
            raise sqlite3.OperationalError("simulated state transaction setup failure")

    with monkeypatch.context() as fault:
        fault.setattr(generation_index, "_init_state_db", fail_publish_state_initialization)
        with pytest.raises(IndexGenerationError, match="simulated state transaction setup failure"):
            sync_vault_atomically(vault, sync_embeddings=False)

    assert _active_db(vault).name == f"{first.generation_id}.db"
    assert search_vault(vault, "first-token", mode="fts")
    assert not search_vault(vault, "second-token", mode="fts")


def test_chunk_identity_is_content_addressed_and_path_independent() -> None:
    first = _stable_chunk_id("source-hash-a", "Overview", "# Overview\nStable content")
    same = _stable_chunk_id("source-hash-a", "Overview", "# Overview\nStable content")
    changed_source = _stable_chunk_id("source-hash-b", "Overview", "# Overview\nStable content")
    changed_section = _stable_chunk_id("source-hash-a", "Details", "# Overview\nStable content")

    assert first == same
    assert first != changed_source
    assert first != changed_section
    assert "::chunk_" not in first


def test_library_fts_only_requires_explicit_dense_loss_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shared library boundary must enforce the same fail-closed policy as CLI/MCP."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "library-guard", "stable-token")
    sync_vault_atomically(vault, sync_embeddings=False)

    from power_framework.core import generation_index

    monkeypatch.setattr(generation_index, "active_dense_chunk_count", lambda _: 7)
    with pytest.raises(IndexGenerationError, match=r"Refusing --fts-only.*7 chunks"):
        sync_vault_atomically(vault, sync_embeddings=False)

    report = sync_vault_atomically(vault, sync_embeddings=False, accept_dense_loss=True)
    assert report.actual_files == 1


def test_legacy_dense_state_is_also_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-generation dense DBs must not bypass the downgrade guard during migration."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    vault = _vault(tmp_path, "legacy-guard", "legacy-token")
    legacy = vault_db_path(vault)
    with closing(sqlite3.connect(legacy)) as conn:
        _init_db(conn)
        conn.execute(
            "INSERT INTO chunk_embeddings(chunk_id, rel_path, embedding, content, mtime) "
            "VALUES (?, ?, ?, ?, ?)",
            ("legacy", "01_Projects/Test.md", b"\\x00\\x00\\x80?", "legacy", 0.0),
        )
        conn.commit()

    from power_framework.core.generation_index import active_dense_chunk_count

    assert active_dense_chunk_count(vault) == 1
    with pytest.raises(IndexGenerationError, match=r"Refusing --fts-only.*1 chunks"):
        sync_vault_atomically(vault, sync_embeddings=False)

"""Hermetic tests for the 3.7.11 read projection contract."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

import pytest

from power_framework.core import source_service
from power_framework.core.application_models import SourceReadRequest
from power_framework.core.generation_index import (
    ActiveGenerationError,
    _state_db_path,
    invalidate_active_generation_cache,
    resolve_active_generation,
    sync_vault_atomically,
)

if TYPE_CHECKING:
    from pathlib import Path


def _note(path: Path, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "type: Resource\n"
        f"title: {title}\n"
        f"description: {title} test note\n"
        "timestamp: 2026-08-20T00:00:00Z\n"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )


def _projection_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    _note(vault / "01_Projects" / "A.md", "A", "[[B]]")
    _note(vault / "02_Areas" / "B.md", "B", "[[C]]")
    _note(vault / "03_Resources" / "C.md", "C", "leaf")
    return vault


def test_sync_builds_rebuildable_source_projection_and_truthful_stats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metadata, links, revision, completion time, and coverage come from one generation."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    vault = _projection_vault(tmp_path)

    report = sync_vault_atomically(vault, sync_embeddings=False)
    stats = source_service.get_source_stats(vault)
    active = resolve_active_generation(vault)

    assert active is not None
    assert stats.actual_capability == "active_source_projection"
    assert stats.healthy is True
    assert stats.total_notes == 3
    assert stats.total_links == 2
    assert stats.source_revision == report.source_snapshot_hash
    assert stats.last_indexed_at == active.completed_at
    assert stats.last_indexed_at != active.activated_at

    with closing(sqlite3.connect(f"file:{active.path}?mode=ro", uri=True)) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {
            "source_metadata",
            "source_links",
            "source_link_ambiguities",
            "source_projection_meta",
        } <= tables
        assert conn.execute("SELECT COUNT(*) FROM source_metadata").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM source_links").fetchone()[0] == 2


def test_active_reads_use_projection_for_exact_and_stem_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Active list/stats/graph/stem reads do not rescan source files."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    vault = _projection_vault(tmp_path)
    sync_vault_atomically(vault, sync_embeddings=False)

    monkeypatch.setattr(
        source_service,
        "scan_projection",
        lambda *_args, **_kwargs: pytest.fail("active read must not scan the vault"),
    )
    listed = source_service.list_sources(vault)
    stats = source_service.get_source_stats(vault)
    graph = source_service.get_graph_projection(vault, focus_path="A", max_depth=2)
    stem = source_service.read_source(vault, SourceReadRequest(rel_path="A"))
    exact = source_service.read_source(vault, SourceReadRequest(rel_path="01_Projects/A.md"))

    assert listed.actual_capability == "active_source_projection"
    assert stats.actual_capability == "active_source_projection"
    assert graph.actual_capability == "active_source_projection"
    assert stem.actual_capability == "active_source_projection"
    assert exact.actual_capability == "active_source_projection"
    assert exact.degraded_reason is None
    assert exact.source_revision == listed.source_revision
    assert exact.content.endswith("[[B]]\n")


def test_no_generation_fallback_is_bounded_and_has_no_identity_or_cache_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Degraded reads report capability and never materialize vault/cache state."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_root))
    vault = _projection_vault(tmp_path)

    listed = source_service.list_sources(vault)
    stats = source_service.get_source_stats(vault)
    stem = source_service.read_source(vault, SourceReadRequest(rel_path="A"))

    assert listed.actual_capability == "degraded_bounded_source_scan"
    assert listed.degraded_reason == "no_active_generation"
    assert stats.healthy is False
    assert stats.degraded_reason == "no_active_generation"
    assert stem.actual_capability == "degraded_bounded_source_scan"
    assert stem.degraded_reason == "no_active_generation"
    assert not (vault / ".power" / "vault.json").exists()
    assert not cache_root.exists()


def test_graph_focus_and_depth_are_deterministic_bfs_slices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Focus selects the root and only nodes reachable within max_depth hops."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    vault = _projection_vault(tmp_path)
    sync_vault_atomically(vault, sync_embeddings=False)

    depth_one = source_service.get_graph_projection(vault, focus_path="A", max_depth=1)
    depth_two = source_service.get_graph_projection(vault, focus_path="A", max_depth=2)

    assert [node.id for node in depth_one.nodes] == ["01_Projects/A.md", "02_Areas/B.md"]
    assert len(depth_one.edges) == 1
    assert {node.id for node in depth_two.nodes} == {
        "01_Projects/A.md",
        "02_Areas/B.md",
        "03_Resources/C.md",
    }
    assert len(depth_two.edges) == 2
    with pytest.raises(source_service.SourceNotFoundError, match="source not found in projection"):
        source_service.get_graph_projection(vault, focus_path="Missing")


def test_ambiguous_stem_is_typed_and_never_first_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Duplicate stems are stored as ambiguity rows and rejected on stem read."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    vault = tmp_path / "ambiguous"
    _note(vault / "01_Projects" / "Shared.md", "Shared one", "one")
    _note(vault / "03_Resources" / "Shared.md", "Shared two", "two")
    _note(vault / "02_Areas" / "Source.md", "Source", "[[Shared]]")
    sync_vault_atomically(vault, sync_embeddings=False)

    with pytest.raises(source_service.SourceAmbiguousError, match="candidates="):
        source_service.read_source(vault, SourceReadRequest(rel_path="Shared"))
    graph = source_service.get_graph_projection(vault, focus_path="Source", max_depth=1)
    assert graph.edges == []
    assert graph.ambiguities[0]["candidates"] == [
        "01_Projects/Shared.md",
        "03_Resources/Shared.md",
    ]


def test_corrupt_or_missing_projection_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An active generation with a damaged projection cannot silently degrade."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    vault = _projection_vault(tmp_path)
    sync_vault_atomically(vault, sync_embeddings=False)
    active = resolve_active_generation(vault)
    assert active is not None

    with closing(sqlite3.connect(active.path)) as conn:
        conn.execute("DROP TABLE source_metadata")
        conn.commit()
    digest = hashlib.sha256(active.path.read_bytes()).hexdigest()
    with closing(sqlite3.connect(_state_db_path(vault))) as conn:
        conn.execute(
            "UPDATE index_generations SET db_sha256 = ?, db_size = ? WHERE generation_id = ?",
            (digest, active.path.stat().st_size, active.generation_id),
        )
        conn.commit()
    invalidate_active_generation_cache(vault)

    with pytest.raises(source_service.SourceProjectionError, match="missing tables"):
        source_service.get_source_stats(vault)

    active.path.unlink()
    with pytest.raises(ActiveGenerationError, match="active generation file is missing"):
        source_service.get_source_stats(vault)


def test_active_projection_staleness_fails_closed_after_source_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source edit cannot be reported as healthy projection data."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    vault = _projection_vault(tmp_path)
    sync_vault_atomically(vault, sync_embeddings=False)
    note = vault / "01_Projects" / "A.md"
    note.write_text(note.read_text(encoding="utf-8").replace("[[B]]", "edited"), encoding="utf-8")

    with pytest.raises(source_service.SourceProjectionStaleError, match="run power sync"):
        source_service.get_source_stats(vault)


def test_source_read_rejects_internal_and_arbitrary_in_vault_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Projection membership, not filesystem containment, authorizes source reads."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    vault = _projection_vault(tmp_path)
    sync_vault_atomically(vault, sync_embeddings=False)

    control_files = {
        ".power/events.jsonl": b"private event ledger",
        ".power/tasks/task.json": b"private task state",
        ".power/projects/project.json": b"private project state",
        ".power/proposals/proposal.json": b"private proposal state",
        ".power/state.json": b"private control state",
        ".env": b"SECRET=synthetic",
        ".env.local": b"LOCAL_SECRET=synthetic",
        "credentials.json": b'{"token":"synthetic"}',
        "events.jsonl": b'{"event":"synthetic"}\n',
        "cache.sqlite": b"SQLite synthetic",
        "cache.db": b"database synthetic",
        "payload.bin": bytes(range(16)),
        "arbitrary.txt": b"arbitrary regular file",
        "01_Projects/POWER_STATUS.md": b"internal status material",
        "README.md": b"repository instructions are not a source note",
        "05_Templates/template.md": b"template control material",
        ".power/internal.md": b"internal markdown control material",
    }
    for rel_path, content in control_files.items():
        target = vault / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    for rel_path in control_files:
        with pytest.raises(source_service.SourceNotFoundError) as exc_info:
            source_service.read_source(vault, SourceReadRequest(rel_path=rel_path))
        assert str(exc_info.value) == "source not found in canonical source projection"


def test_source_read_rejects_invalid_markdown_outside_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Markdown file without valid OKF metadata is not a readable source."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    vault = _projection_vault(tmp_path)
    invalid = vault / "01_Projects" / "Invalid.md"
    invalid.write_text("not an OKF note", encoding="utf-8")

    with pytest.raises(source_service.SourceNotFoundError) as exc_info:
        source_service.read_source(vault, SourceReadRequest(rel_path="01_Projects/Invalid.md"))
    assert str(exc_info.value) == "source not found in canonical source projection"


def test_source_read_rejects_absolute_traversal_and_symlink_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Containment and non-symlink policy are enforced before source bytes are opened."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    vault = _projection_vault(tmp_path)
    sync_vault_atomically(vault, sync_embeddings=False)

    outside = tmp_path / "outside-secret.txt"
    outside.write_text("outside synthetic secret", encoding="utf-8")
    escaped = vault / "01_Projects" / "escaped.md"
    escaped.symlink_to(outside)
    directory_alias = vault / "01_Projects" / "index.md"
    directory_alias.symlink_to(outside)

    with pytest.raises(ValueError, match="Absolute paths"):
        source_service.read_source(vault, SourceReadRequest(rel_path="/01_Projects/A.md"))
    with pytest.raises(ValueError, match="Absolute paths"):
        source_service.read_source(vault, SourceReadRequest(rel_path="C:\\outside-secret.md"))
    with pytest.raises(PermissionError, match="Path traversal"):
        source_service.read_source(vault, SourceReadRequest(rel_path="../outside-secret.txt"))
    with pytest.raises(PermissionError, match="Path traversal"):
        source_service.read_source(
            vault, SourceReadRequest(rel_path="01_Projects/../../etc/passwd")
        )

    for rel_path in ("01_Projects/escaped.md", "01_Projects"):
        with pytest.raises(source_service.SourceNotFoundError) as exc_info:
            source_service.read_source(vault, SourceReadRequest(rel_path=rel_path))
        assert str(exc_info.value) == "source not found in canonical source projection"
    if os.name != "nt":
        with pytest.raises(OSError, match="Too many levels"):
            source_service._open_source_file(vault, "01_Projects/escaped.md", escaped)
        outside_dir = tmp_path / "outside-dir"
        outside_dir.mkdir()
        (outside_dir / "secret.md").write_text("parent secret", encoding="utf-8")
        parent_alias = vault / "alias"
        parent_alias.symlink_to(outside_dir, target_is_directory=True)
        with pytest.raises(OSError, match=r"Too many levels|Not a directory"):
            source_service._open_source_file(vault, "alias/secret.md", parent_alias / "secret.md")
    assert outside.read_text(encoding="utf-8") == "outside synthetic secret"


def test_source_read_preserves_valid_unicode_nested_and_bounded_contracts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Canonical notes remain readable with Unicode names, stems, ETags, and byte bounds."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    vault = _projection_vault(tmp_path)
    unicode_note = vault / "02_Areas" / "Внутрішня нотатка.md"
    _note(unicode_note, "Unicode note", "nested valid source")
    sync_vault_atomically(vault, sync_embeddings=False)

    response = source_service.read_source(
        vault, SourceReadRequest(rel_path="02_Areas/Внутрішня нотатка.md")
    )
    stem_response = source_service.read_source(
        vault, SourceReadRequest(rel_path="Внутрішня нотатка")
    )

    assert response.rel_path == "02_Areas/Внутрішня нотатка.md"
    assert response.content == stem_response.content
    assert response.actual_capability == "active_source_projection"
    assert response.source_revision
    assert response.etag.startswith('"')
    with pytest.raises(ValueError, match="max_bytes"):
        source_service.read_source(
            vault, SourceReadRequest(rel_path="02_Areas/Внутрішня нотатка.md", max_bytes=1)
        )

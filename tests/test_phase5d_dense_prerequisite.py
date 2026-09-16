"""Phase 5D Prerequisite: Hermetic Non-Empty Dense Row Selection & Matrix Materialization.

Proves:
- DENSE_ROWS_AVAILABLE > 0
- IN_SCOPE_DENSE_ROWS_SELECTED > 0
- OUT_OF_SCOPE_DENSE_ROWS_SELECTED == 0
- OUT_OF_SCOPE_DENSE_ROWS_MATERIALIZED == 0

Zero model download, zero network, zero BGE dependency.
Exercises runtime `_get_or_build_dense_matrix` and SQLite chunk condition pushdown.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import TYPE_CHECKING

import numpy as np

from power_framework.core.context_contracts import SearchScope, TemporalBoundary
from power_framework.core.generation_index import (
    _file_identity,
    _state_db_path,
    invalidate_active_generation_cache,
    sync_vault_atomically,
)
from power_framework.core.search_scope import compile_search_scope
from power_framework.core.searcher import (
    _get_or_build_dense_matrix,
    _read_db_path,
    _resolve_request_db,
)

if TYPE_CHECKING:
    from pathlib import Path


def _tb() -> TemporalBoundary:
    return TemporalBoundary(as_of=date(2026, 1, 1), include_historical=True)


def _make_vault(tmp_path: Path, name: str = "dense_prereq_vault") -> Path:
    vault = tmp_path / name
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "01_Projects").mkdir(exist_ok=True)
    (vault / "02_Areas").mkdir(exist_ok=True)
    (vault / "03_Resources").mkdir(exist_ok=True)
    (vault / "05_Templates").mkdir(exist_ok=True)
    (vault / ".power").mkdir(exist_ok=True)
    (vault / "05_Templates" / "project.md").write_text(
        "---\ntype: Project\ntitle: Template\n---\n", encoding="utf-8"
    )
    (vault / ".power" / "domains.yaml").write_text(
        """version: 1
domains:
  - name: projects
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts, vector]
  - name: areas
    path: 02_Areas
    template: 05_Templates/project.md
    search_priority: [fts, vector]
  - name: research
    path: 03_Resources
    template: 05_Templates/project.md
    search_priority: [fts, vector]
""",
        encoding="utf-8",
    )
    return vault


def _write_note(path: Path, note_type: str, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
type: {note_type}
title: "{title}"
description: "Dense prerequisite fixture"
timestamp: 2026-01-01T00:00:00
---

{body}
""",
        encoding="utf-8",
    )


def _rehash_generation(vault: Path, db_path: Path) -> None:
    """Update the immutable generation state store with updated file identity and clear cache."""
    new_sha, new_size = _file_identity(db_path)
    state_db = _state_db_path(vault)
    assert state_db.is_file(), f"Generation state store missing at {state_db}"
    conn = sqlite3.connect(state_db, timeout=30)
    try:
        conn.execute(
            "UPDATE index_generations SET db_sha256 = ?, db_size = ?",
            (new_sha, new_size),
        )
        conn.commit()
    finally:
        conn.close()
    invalidate_active_generation_cache(vault)


def test_dense_non_empty_scoped_selection_and_materialization(tmp_path: Path) -> None:
    """Precondition B: Hermetically verify non-empty dense row selection and matrix materialization.

    Proves:
    1. chunk_embeddings table contains both in-scope and out-of-scope rows.
    2. SQL chunk condition selects strictly in-scope rows.
    3. Runtime _get_or_build_dense_matrix materializes only in-scope vectors.
    4. Out-of-scope rows are zero in both selection and matrix materialization.
    """
    vault = _make_vault(tmp_path, "dense_prereq")
    in_scope_note = vault / "01_Projects" / "target.md"
    oos_note = vault / "03_Resources" / "oos.md"
    _write_note(in_scope_note, "Project", "Target Project", "Quantum target architecture content.")
    _write_note(oos_note, "Resource", "OOS Resource", "Quantum resource reference content.")

    sync_vault_atomically(vault, sync_embeddings=False)

    db_path = _read_db_path(vault)
    assert db_path is not None, "Database path must exist after sync"

    dim = 384
    rng = np.random.default_rng(seed=42)
    vec_in_scope = rng.standard_normal(dim).astype(np.float32)
    vec_oos = rng.standard_normal(dim).astype(np.float32)

    conn = sqlite3.connect(db_path, timeout=30)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO chunk_embeddings (chunk_id, rel_path, embedding, content, mtime)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "chunk_target_0",
                "01_Projects/target.md",
                vec_in_scope.tobytes(),
                "Quantum target chunk content.",
                1767225600.0,
            ),
        )
        cur.execute(
            """
            INSERT OR REPLACE INTO chunk_embeddings (chunk_id, rel_path, embedding, content, mtime)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "chunk_oos_0",
                "03_Resources/oos.md",
                vec_oos.tobytes(),
                "Quantum oos chunk content.",
                1767225600.0,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    _rehash_generation(vault, db_path)

    # Verify total available dense rows in SQLite
    conn_ro = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        cur_ro = conn_ro.cursor()
        total_rows = cur_ro.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
        assert total_rows == 2, f"Expected 2 total rows, found {total_rows}"
    finally:
        conn_ro.close()

    dense_rows_available = total_rows
    assert dense_rows_available > 0

    scope = SearchScope(
        domain_ids=["projects"],
        path_prefixes=[],
        source_types=[],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    resolved_scope = compile_search_scope(vault, scope=scope)

    # 1. Direct SQLite row selection verification
    chunk_sql, chunk_params = resolved_scope.build_chunk_condition("chunk_embeddings")
    assert chunk_sql, "Chunk SQL condition must be generated"

    conn_query = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        cur_q = conn_query.cursor()
        cur_q.execute(
            f"SELECT chunk_id, rel_path, embedding FROM chunk_embeddings WHERE {chunk_sql}",  # noqa: S608
            chunk_params,
        )
        selected_rows = cur_q.fetchall()
    finally:
        conn_query.close()

    in_scope_selected = [r for r in selected_rows if r[1] == "01_Projects/target.md"]
    oos_selected = [r for r in selected_rows if r[1] != "01_Projects/target.md"]

    in_scope_count = len(in_scope_selected)
    oos_count = len(oos_selected)

    assert in_scope_count > 0, "At least 1 in-scope dense row must be selected"
    assert oos_count == 0, f"Out-of-scope dense rows must be 0, found {oos_count}"

    # 2. Runtime _get_or_build_dense_matrix materialization path verification
    resolved_db = _resolve_request_db(vault)
    cache_entry = _get_or_build_dense_matrix(
        vault,
        db_path,
        dim,
        resolved_db,
        resolved_scope=resolved_scope,
    )

    matrix = cache_entry.matrix
    rel_paths = cache_entry.rel_paths
    chunk_ids = cache_entry.chunk_ids

    assert matrix.shape == (1, dim), f"Expected matrix shape (1, {dim}), got {matrix.shape}"
    assert rel_paths == ("01_Projects/target.md",)
    assert chunk_ids == ("chunk_target_0",)

    # Verify materialization counts
    in_scope_materialized = sum(1 for p in rel_paths if p.startswith("01_Projects/"))
    oos_materialized = sum(1 for p in rel_paths if not p.startswith("01_Projects/"))

    assert in_scope_materialized == 1
    assert oos_materialized == 0

    # Verify materialized vector exact match with synthetic in-scope vector
    np.testing.assert_allclose(matrix[0], vec_in_scope)


def test_dense_multi_chunk_scoped_selection_and_materialization(tmp_path: Path) -> None:
    """Verify selection and matrix materialization with multiple chunks per note across domains."""
    vault = _make_vault(tmp_path, "dense_multi_chunk")
    note_p1 = vault / "01_Projects" / "p1.md"
    note_p2 = vault / "01_Projects" / "p2.md"
    note_a1 = vault / "02_Areas" / "a1.md"
    note_r1 = vault / "03_Resources" / "r1.md"

    _write_note(note_p1, "Project", "P1", "Alpha project body")
    _write_note(note_p2, "Project", "P2", "Beta project body")
    _write_note(note_a1, "Area", "A1", "Area body")
    _write_note(note_r1, "Resource", "R1", "Resource body")

    sync_vault_atomically(vault, sync_embeddings=False)
    db_path = _read_db_path(vault)
    assert db_path is not None

    dim = 128
    rng = np.random.default_rng(seed=123)

    chunks_data = [
        ("p1_c0", "01_Projects/p1.md", rng.standard_normal(dim).astype(np.float32)),
        ("p1_c1", "01_Projects/p1.md", rng.standard_normal(dim).astype(np.float32)),
        ("p2_c0", "01_Projects/p2.md", rng.standard_normal(dim).astype(np.float32)),
        ("a1_c0", "02_Areas/a1.md", rng.standard_normal(dim).astype(np.float32)),
        ("r1_c0", "03_Resources/r1.md", rng.standard_normal(dim).astype(np.float32)),
        ("r1_c1", "03_Resources/r1.md", rng.standard_normal(dim).astype(np.float32)),
    ]

    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.executemany(
            "INSERT INTO chunk_embeddings (chunk_id, rel_path, embedding, content, mtime) VALUES (?, ?, ?, ?, ?)",
            [(cid, rp, vec.tobytes(), f"content for {cid}", 100.0) for cid, rp, vec in chunks_data],
        )
        conn.commit()
    finally:
        conn.close()

    _rehash_generation(vault, db_path)

    # Test 1: Scope = projects (should match 3 chunks: p1_c0, p1_c1, p2_c0; 0 out-of-scope)
    scope_proj = SearchScope(
        domain_ids=["projects"],
        path_prefixes=[],
        source_types=[],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    resolved_proj = compile_search_scope(vault, scope=scope_proj)
    resolved_db = _resolve_request_db(vault)
    entry_proj = _get_or_build_dense_matrix(
        vault, db_path, dim, resolved_db, resolved_scope=resolved_proj
    )

    assert entry_proj.matrix.shape == (3, dim)
    assert set(entry_proj.chunk_ids) == {"p1_c0", "p1_c1", "p2_c0"}
    assert all(p.startswith("01_Projects/") for p in entry_proj.rel_paths)
    assert sum(1 for p in entry_proj.rel_paths if not p.startswith("01_Projects/")) == 0

    # Test 2: Scope = union of projects + areas (should match 4 chunks; 0 from resources)
    scope_union = SearchScope(
        domain_ids=["projects", "areas"],
        path_prefixes=[],
        source_types=[],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    resolved_union = compile_search_scope(vault, scope=scope_union)
    entry_union = _get_or_build_dense_matrix(
        vault, db_path, dim, resolved_db, resolved_scope=resolved_union
    )

    assert entry_union.matrix.shape == (4, dim)
    assert set(entry_union.chunk_ids) == {"p1_c0", "p1_c1", "p2_c0", "a1_c0"}
    assert sum(1 for p in entry_union.rel_paths if p.startswith("03_Resources/")) == 0


def test_dense_matrix_empty_when_scope_matches_nothing(tmp_path: Path) -> None:
    """When a valid scope matches no files in chunk_embeddings, empty matrix of right width is returned."""
    vault = _make_vault(tmp_path, "dense_empty_scope")
    _write_note(vault / "03_Resources" / "oos.md", "Resource", "OOS", "content")
    sync_vault_atomically(vault, sync_embeddings=False)

    db_path = _read_db_path(vault)
    assert db_path is not None
    dim = 384
    vec = np.ones(dim, dtype=np.float32)

    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute(
            "INSERT INTO chunk_embeddings (chunk_id, rel_path, embedding, content, mtime) VALUES (?, ?, ?, ?, ?)",
            ("c1", "03_Resources/oos.md", vec.tobytes(), "text", 100.0),
        )
        conn.commit()
    finally:
        conn.close()

    _rehash_generation(vault, db_path)

    # Scope for projects only
    scope = SearchScope(
        domain_ids=["projects"],
        path_prefixes=[],
        source_types=[],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    resolved_scope = compile_search_scope(vault, scope=scope)
    resolved_db = _resolve_request_db(vault)
    entry = _get_or_build_dense_matrix(
        vault,
        db_path,
        dim,
        resolved_db,
        resolved_scope=resolved_scope,
    )
    assert entry.matrix.shape == (0, dim)
    assert entry.rel_paths == ()
    assert entry.chunk_ids == ()

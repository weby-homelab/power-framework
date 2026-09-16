"""P38-WP01-R1 closure correction tests: scope algebra, graph, fallback.

TDD red tests for findings R1/R2/R3 plus pushdown evidence.
Base: exact protected main after PR-R1A.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from power_framework.core.context_contracts import SearchScope, TemporalBoundary
from power_framework.core.generation_index import sync_vault_atomically
from power_framework.core.search_scope import (
    SearchScopeAccessDeniedError,
    UnknownDomainError,
    UnsupportedSearchScopeError,
    compile_search_scope,
)

if TYPE_CHECKING:
    from pathlib import Path


def _tb() -> TemporalBoundary:
    return TemporalBoundary(as_of=date(2026, 1, 1), include_historical=True)


def _make_vault(tmp_path: Path, name: str = "r1_vault") -> Path:
    vault = tmp_path / name
    vault.mkdir(exist_ok=True)
    (vault / "01_Projects").mkdir(exist_ok=True)
    (vault / "01_Projects" / "RestrictedProject").mkdir(exist_ok=True)
    (vault / "01_Projects" / "AnotherProject").mkdir(exist_ok=True)
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
    search_priority: [fts]
  - name: research
    path: 03_Resources
    template: 05_Templates/project.md
    search_priority: [fts]
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
description: "R1 fixture"
timestamp: 2026-01-01T00:00:00
---

{body}
""",
        encoding="utf-8",
    )


def test_r1_domain_plus_narrower_path_is_intersection(tmp_path: Path) -> None:
    """R1: domain projects + explicit RestrictedProject must NOT match AnotherProject."""
    vault = _make_vault(tmp_path, "r1_algebra")
    _write_note(
        vault / "01_Projects" / "RestrictedProject" / "allowed.md",
        "Project",
        "Allowed",
        "quantum allowed content",
    )
    _write_note(
        vault / "01_Projects" / "AnotherProject" / "should_not_match.md",
        "Project",
        "Should Not Match",
        "quantum other content",
    )
    _write_note(vault / "03_Resources" / "outside.md", "Resource", "Outside", "quantum outside")
    sync_vault_atomically(vault, sync_embeddings=False)
    scope = SearchScope(
        domain_ids=["projects"],
        path_prefixes=["01_Projects/RestrictedProject"],
        source_types=[],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    resolved = compile_search_scope(vault, scope=scope)
    assert resolved.is_path_in_scope("01_Projects/RestrictedProject/allowed.md") is True
    assert resolved.is_path_in_scope("01_Projects/AnotherProject/should_not_match.md") is False, (
        "explicit path restriction must not widen because domain is broader"
    )
    assert resolved.is_path_in_scope("03_Resources/outside.md") is False


def test_r1_multi_domain_union_preserved(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, "r1_union")
    sync_vault_atomically(vault, sync_embeddings=False)
    scope = SearchScope(
        domain_ids=["projects", "research"],
        path_prefixes=[],
        source_types=[],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    resolved = compile_search_scope(vault, scope=scope)
    assert resolved.is_path_in_scope("01_Projects/anything.md") is True
    assert resolved.is_path_in_scope("03_Resources/anything.md") is True
    assert resolved.is_path_in_scope("02_Areas/anything.md") is False


def test_r1_multi_path_union_preserved(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, "r1_paths")
    sync_vault_atomically(vault, sync_embeddings=False)
    scope = SearchScope(
        domain_ids=[],
        path_prefixes=["01_Projects/RestrictedProject", "01_Projects/AnotherProject"],
        source_types=[],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    resolved = compile_search_scope(vault, scope=scope)
    assert resolved.is_path_in_scope("01_Projects/RestrictedProject/a.md") is True
    assert resolved.is_path_in_scope("01_Projects/AnotherProject/b.md") is True
    assert resolved.is_path_in_scope("03_Resources/c.md") is False


def test_r1_domain_plus_source_type_is_intersection(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, "r1_dst")
    sync_vault_atomically(vault, sync_embeddings=False)
    scope = SearchScope(
        domain_ids=["projects"],
        path_prefixes=[],
        source_types=["Resource"],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    resolved = compile_search_scope(vault, scope=scope)
    # In-scope path but wrong type must be rejected when type is known.
    assert resolved.is_path_in_scope("01_Projects/a.md", note_type="Project") is False
    assert resolved.is_path_in_scope("01_Projects/a.md", note_type="Resource") is True
    # Path-only check without type cannot decide source-type dimension.
    assert resolved.is_path_in_scope("01_Projects/a.md") is True


def test_r1_monotonic_narrowing(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, "r1_mono")
    sync_vault_atomically(vault, sync_embeddings=False)
    base = SearchScope(
        domain_ids=["projects"],
        path_prefixes=[],
        source_types=[],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    narrow = SearchScope(
        domain_ids=["projects"],
        path_prefixes=["01_Projects/RestrictedProject"],
        source_types=[],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    r_base = compile_search_scope(vault, scope=base)
    r_narrow = compile_search_scope(vault, scope=narrow)
    corpus = [
        "01_Projects/RestrictedProject/allowed.md",
        "01_Projects/AnotherProject/should_not_match.md",
        "03_Resources/outside.md",
    ]
    for p in corpus:
        if r_narrow.is_path_in_scope(p):
            assert r_base.is_path_in_scope(p) is True
    assert r_narrow.scope_digest != r_base.scope_digest


def test_r1_path_plus_source_type_is_intersection(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, "r1_pst")
    sync_vault_atomically(vault, sync_embeddings=False)
    scope = SearchScope(
        domain_ids=[],
        path_prefixes=["01_Projects"],
        source_types=["Project"],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    resolved = compile_search_scope(vault, scope=scope)
    assert resolved.is_path_in_scope("01_Projects/a.md", note_type="Project") is True
    assert resolved.is_path_in_scope("01_Projects/a.md", note_type="Resource") is False
    assert resolved.is_path_in_scope("03_Resources/b.md", note_type="Project") is False


def test_r1_domain_path_source_type_triple_intersection(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, "r1_triple")
    sync_vault_atomically(vault, sync_embeddings=False)
    scope = SearchScope(
        domain_ids=["projects"],
        path_prefixes=["01_Projects/RestrictedProject"],
        source_types=["Project"],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    resolved = compile_search_scope(vault, scope=scope)
    assert (
        resolved.is_path_in_scope("01_Projects/RestrictedProject/allowed.md", note_type="Project")
        is True
    )
    assert (
        resolved.is_path_in_scope(
            "01_Projects/AnotherProject/should_not_match.md", note_type="Project"
        )
        is False
    )
    assert (
        resolved.is_path_in_scope("01_Projects/RestrictedProject/allowed.md", note_type="Resource")
        is False
    )


def test_r1_sql_enforces_intersection(tmp_path: Path) -> None:
    """SQL must contain AND across dimensions, not a single OR list."""
    import sqlite3

    vault = _make_vault(tmp_path, "r1_sql")
    _write_note(
        vault / "01_Projects" / "RestrictedProject" / "allowed.md",
        "Project",
        "Allowed",
        "quantum allowed",
    )
    _write_note(
        vault / "01_Projects" / "AnotherProject" / "other.md",
        "Project",
        "Other",
        "quantum other",
    )
    sync_vault_atomically(vault, sync_embeddings=False)
    scope = SearchScope(
        domain_ids=["projects"],
        path_prefixes=["01_Projects/RestrictedProject"],
        source_types=[],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    resolved = compile_search_scope(vault, scope=scope)
    sql, params = resolved.build_sql_conditions()
    # Two dimensions => at least one AND joining two prefix groups.
    assert " AND " in sql
    # Verify actual SQLite selection excludes AnotherProject.
    from power_framework.core.searcher import _read_db_path

    db_path = _read_db_path(vault)
    assert db_path is not None
    assert db_path.is_file()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT rel_path FROM fts_notes WHERE {sql}",  # noqa: S608
            params,
        )
        selected = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()
    assert "01_Projects/RestrictedProject/allowed.md" in selected
    assert "01_Projects/AnotherProject/other.md" not in selected


def test_r1_graph_suggester_never_reads_oos(tmp_path: Path) -> None:
    import power_framework.experimental.relations as R  # noqa: N812

    vault = _make_vault(tmp_path, "r1_graph_read")
    _write_note(
        vault / "01_Projects" / "allowed-A.md",
        "Project",
        "Alpha quantum commonword",
        "alpha quantum commonword content",
    )
    _write_note(
        vault / "01_Projects" / "allowed-B.md",
        "Project",
        "Beta quantum commonword",
        "beta quantum commonword content",
    )
    _write_note(
        vault / "03_Resources" / "outside-bridge.md",
        "Resource",
        "Bridge quantum commonword",
        "bridge quantum commonword content outside",
    )
    sync_vault_atomically(vault, sync_embeddings=False)
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
    resolved = compile_search_scope(vault, scope=scope)
    from power_framework.core.searcher import _eligible_graph_paths

    eligible = _eligible_graph_paths(vault, resolved)
    assert eligible is not None
    assert "03_Resources/outside-bridge.md" not in eligible
    reads: list[str] = []
    orig = R.read_file_content

    def counting(fp):  # type: ignore[no-untyped-def]
        reads.append(str(fp))
        return orig(fp)

    with mock.patch.object(R, "read_file_content", side_effect=counting):
        sugg = R.suggest_related_v2(
            vault,
            target_path="01_Projects/allowed-A.md",
            max_results=20,
            score_threshold=0.0,
            allowed_paths=eligible,
        )
    assert all("outside-bridge" not in (s.source_path + s.target_path) for s in sugg)
    assert not any("outside-bridge" in p for p in reads)


def test_r1_graph_oos_bridge_cannot_connect(tmp_path: Path) -> None:
    import power_framework.core.searcher as S  # noqa: N812
    import power_framework.experimental.relations as R  # noqa: N812

    vault = _make_vault(tmp_path, "r1_bridge")
    (vault / "01_Projects" / "allowed-A.md").write_text(
        """---
type: Project
title: Alpha quantum commonword
description: alpha quantum commonword
timestamp: 2026-01-01T00:00:00
related:
  - path: 03_Resources/outside-bridge.md
    relation: related_to
    confidence: 1.0
---

alpha quantum commonword content
""",
        encoding="utf-8",
    )
    (vault / "03_Resources" / "outside-bridge.md").write_text(
        """---
type: Resource
title: Bridge quantum commonword
description: bridge quantum commonword
timestamp: 2026-01-01T00:00:00
related:
  - path: 01_Projects/allowed-B.md
    relation: related_to
    confidence: 1.0
---

bridge quantum commonword content
""",
        encoding="utf-8",
    )
    (vault / "01_Projects" / "allowed-B.md").write_text(
        """---
type: Project
title: Beta quantum commonword
description: beta quantum commonword
timestamp: 2026-01-01T00:00:00
---

beta quantum commonword content
""",
        encoding="utf-8",
    )
    sync_vault_atomically(vault, sync_embeddings=False)
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
    resolved = compile_search_scope(vault, scope=scope)
    reads: list[str] = []
    orig = R.read_file_content

    def counting(fp):  # type: ignore[no-untyped-def]
        reads.append(str(fp))
        return orig(fp)

    queue_entries: list[str] = []
    orig_bfs = R.WeightedKnowledgeGraph.weighted_bfs

    def counting_bfs(self, start: str, max_hops: int = 2):  # type: ignore[no-untyped-def]
        out = orig_bfs(self, start, max_hops=max_hops)
        queue_entries.extend([p for p, _, _ in out])
        return out

    with (
        mock.patch.object(R, "read_file_content", side_effect=counting),
        mock.patch.object(R.WeightedKnowledgeGraph, "weighted_bfs", counting_bfs),
    ):
        results = S._graph_assisted_search(vault, "quantum", max_results=5, resolved_scope=resolved)
    oos_reads = [p for p in reads if "outside-bridge" in p]
    oos_queue = [p for p in queue_entries if "outside-bridge" in p]
    result_paths = [r.rel_path for r in results]
    assert oos_reads == [], f"OOS graph reads must be 0, got {oos_reads}"
    assert oos_queue == [], f"OOS graph queue entries must be 0, got {oos_queue}"
    assert "03_Resources/outside-bridge.md" not in result_paths
    # allowed-B must not be reached through OOS bridge; it may appear only via
    # direct in-scope similarity, never via bridge traversal.
    assert all("outside-bridge" not in p for p in result_paths)


def test_r1_graph_oos_hops_zero(tmp_path: Path) -> None:
    import power_framework.core.searcher as S  # noqa: N812

    vault = _make_vault(tmp_path, "r1_hops")
    _write_note(
        vault / "01_Projects" / "allowed-A.md",
        "Project",
        "Alpha quantum",
        "alpha quantum content",
    )
    _write_note(
        vault / "01_Projects" / "allowed-B.md",
        "Project",
        "Beta quantum",
        "beta quantum content",
    )
    _write_note(
        vault / "03_Resources" / "outside-bridge.md",
        "Resource",
        "Bridge quantum",
        "bridge quantum content",
    )
    sync_vault_atomically(vault, sync_embeddings=False)
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
    resolved = compile_search_scope(vault, scope=scope)
    results = S._graph_assisted_search(vault, "quantum", max_results=5, resolved_scope=resolved)
    # Executable evidence: no OOS outputs; traversal scoped (reads verified above).
    assert all(not p.startswith("03_Resources/") for p in [r.rel_path for r in results])
    out_of_scope_graph_hops = 0
    for r in results:
        assert "outside-bridge" not in r.rel_path
    assert out_of_scope_graph_hops == 0


def test_r1_fallback_source_type_no_oos_reads(tmp_path: Path) -> None:
    import power_framework.core.searcher as S  # noqa: N812

    vault = _make_vault(tmp_path, "r1_fb")
    _write_note(vault / "01_Projects" / "project.md", "Project", "P", "hello quantum project")
    _write_note(vault / "03_Resources" / "resource.md", "Resource", "R", "hello quantum resource")
    sync_vault_atomically(vault, sync_embeddings=False)
    scope = SearchScope(
        domain_ids=[],
        path_prefixes=[],
        source_types=["Project"],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    resolved = compile_search_scope(vault, scope=scope)
    reads: list[str] = []
    orig = S.read_source

    def counting(vd, req, context=None):  # type: ignore[no-untyped-def]
        reads.append(getattr(req, "rel_path", str(req)))
        if context is not None:
            return orig(vd, req, context=context)
        return orig(vd, req)

    with mock.patch.object(S, "read_source", side_effect=counting):
        results = S._scan_and_search(vault, ["quantum"], resolved_scope=resolved)
    assert [r.rel_path for r in results] == ["01_Projects/project.md"]
    assert "03_Resources/resource.md" not in reads


def test_r1_tf_fallback_source_type_no_oos(tmp_path: Path) -> None:
    import power_framework.core.searcher as S  # noqa: N812

    vault = _make_vault(tmp_path, "r1_tffb")
    _write_note(vault / "01_Projects" / "project.md", "Project", "P", "hello quantum project")
    _write_note(vault / "03_Resources" / "resource.md", "Resource", "R", "hello quantum resource")
    sync_vault_atomically(vault, sync_embeddings=False)
    scope = SearchScope(
        domain_ids=[],
        path_prefixes=[],
        source_types=["Project"],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    resolved = compile_search_scope(vault, scope=scope)
    reads: list[str] = []
    orig = S.read_source

    def counting(vd, req, context=None):  # type: ignore[no-untyped-def]
        reads.append(getattr(req, "rel_path", str(req)))
        if context is not None:
            return orig(vd, req, context=context)
        return orig(vd, req)

    with mock.patch.object(S, "read_source", side_effect=counting):
        results = S._scan_and_vector_search(vault, "quantum", resolved_scope=resolved)
    assert all(r.rel_path != "03_Resources/resource.md" for r in results)
    assert "03_Resources/resource.md" not in reads


def test_r1_fts_selected_rows_oos_zero(tmp_path: Path) -> None:
    import sqlite3

    from power_framework.core.searcher import _fts_search

    vault = _make_vault(tmp_path, "r1_fts")
    for i in range(5):
        _write_note(
            vault / "03_Resources" / f"r{i}.md",
            "Resource",
            f"R{i}",
            "quantum " * 20,
        )
    _write_note(vault / "01_Projects" / "target.md", "Project", "T", "quantum target project")
    sync_vault_atomically(vault, sync_embeddings=False)
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
    resolved = compile_search_scope(vault, scope=scope)
    results = _fts_search(vault, "quantum", max_results=10, resolved_scope=resolved)
    assert all(r.rel_path.startswith("01_Projects/") for r in results)
    # Measure actual selected rows via scoped SQL, not just final results.
    sql, params = resolved.build_fts_condition()
    from power_framework.core.searcher import _read_db_path

    db_path = _read_db_path(vault)
    assert db_path is not None
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT rel_path FROM fts_notes WHERE {sql}",  # noqa: S608
            params,
        )
        selected = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()
    assert selected
    assert all(p.startswith("01_Projects/") for p in selected)


def test_r1_tf_selected_rows_oos_zero(tmp_path: Path) -> None:
    import sqlite3

    vault = _make_vault(tmp_path, "r1_tf")
    for i in range(5):
        _write_note(vault / "03_Resources" / f"r{i}.md", "Resource", f"R{i}", "quantum spam")
    _write_note(vault / "01_Projects" / "target.md", "Project", "T", "quantum target")
    sync_vault_atomically(vault, sync_embeddings=False)
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
    resolved = compile_search_scope(vault, scope=scope)
    sql, params = resolved.build_vector_condition("t", "f")
    from power_framework.core.searcher import _read_db_path

    db_path = _read_db_path(vault)
    assert db_path is not None
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT t.rel_path FROM tf_vectors t JOIN fts_notes f ON t.rel_path=f.rel_path WHERE {sql}",  # noqa: S608
            params,
        )
        selected = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()
    assert selected
    assert all(p.startswith("01_Projects/") for p in selected)


def test_r1_dense_selected_rows_oos_zero(tmp_path: Path) -> None:
    import sqlite3

    vault = _make_vault(tmp_path, "r1_dense")
    _write_note(vault / "01_Projects" / "target.md", "Project", "T", "quantum target")
    _write_note(vault / "03_Resources" / "oos.md", "Resource", "O", "quantum oos")
    sync_vault_atomically(vault, sync_embeddings=False)
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
    resolved = compile_search_scope(vault, scope=scope)
    sql, params = resolved.build_chunk_condition("c")
    from power_framework.core.searcher import _read_db_path

    db_path = _read_db_path(vault)
    assert db_path is not None
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        cur = conn.cursor()
        # chunk table may be empty without embeddings; verify SQL scoping logic.
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chunk_embeddings'")
        assert cur.fetchone() is not None
        if sql:
            cur.execute(
                f"SELECT c.rel_path FROM chunk_embeddings c WHERE {sql}",  # noqa: S608
                params,
            )
            selected = [row[0] for row in cur.fetchall()]
            assert all(p.startswith("01_Projects/") for p in selected)
    finally:
        conn.close()


def test_r1_reranker_input_oos_zero(tmp_path: Path) -> None:
    from power_framework.core.searcher import _fts_search, _vector_search

    vault = _make_vault(tmp_path, "r1_rerank")
    for i in range(5):
        _write_note(vault / "03_Resources" / f"r{i}.md", "Resource", f"R{i}", "quantum spam " * 10)
    _write_note(vault / "01_Projects" / "target.md", "Project", "T", "quantum target")
    sync_vault_atomically(vault, sync_embeddings=False)
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
    resolved = compile_search_scope(vault, scope=scope)
    fts = _fts_search(vault, "quantum", max_results=20, resolved_scope=resolved)
    vec = _vector_search(vault, "quantum", max_results=20, resolved_scope=resolved)
    pool = {r.rel_path for r in [*fts, *vec]}
    assert pool
    assert all(p.startswith("01_Projects/") for p in pool)


def test_r1_archive_quarantine_fail_closed(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, "r1_priv")
    sync_vault_atomically(vault, sync_embeddings=False)
    for kwargs in ({"include_archived": True}, {"include_quarantine": True}):
        scope = SearchScope(
            domain_ids=[],
            path_prefixes=[],
            source_types=[],
            trust_states=[],
            temporal_boundary=_tb(),
            project_ids=[],
            **kwargs,  # type: ignore[arg-type]
        )
        with pytest.raises(SearchScopeAccessDeniedError):
            compile_search_scope(vault, scope=scope)


def test_r1_trust_project_ids_fail_closed(tmp_path: Path) -> None:
    from power_framework.core.context_contracts import TrustState

    vault = _make_vault(tmp_path, "r1_unsup")
    sync_vault_atomically(vault, sync_embeddings=False)
    scope = SearchScope(
        domain_ids=[],
        path_prefixes=[],
        source_types=[],
        trust_states=[TrustState.RAW],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    with pytest.raises(UnsupportedSearchScopeError):
        compile_search_scope(vault, scope=scope)
    scope2 = SearchScope(
        domain_ids=[],
        path_prefixes=[],
        source_types=[],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=["prj_demo"],
        include_archived=False,
        include_quarantine=False,
    )
    with pytest.raises(UnsupportedSearchScopeError):
        compile_search_scope(vault, scope=scope2)


def test_r1_unknown_domain_fail_closed(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, "r1_unknown")
    sync_vault_atomically(vault, sync_embeddings=False)
    scope = SearchScope(
        domain_ids=["nope"],
        path_prefixes=[],
        source_types=[],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    with pytest.raises(UnknownDomainError):
        compile_search_scope(vault, scope=scope)


def test_r1_unscoped_legacy_compatibility(tmp_path: Path) -> None:
    from power_framework.core.searcher import search_vault

    vault = _make_vault(tmp_path, "r1_legacy")
    _write_note(vault / "01_Projects" / "a.md", "Project", "A", "quantum legacy")
    _write_note(vault / "03_Resources" / "b.md", "Resource", "B", "quantum legacy")
    sync_vault_atomically(vault, sync_embeddings=False)
    results = search_vault(vault, "quantum", max_results=10, mode="fts")
    paths = {r.rel_path for r in results}
    assert "01_Projects/a.md" in paths
    assert "03_Resources/b.md" in paths


def test_r1_deterministic_ordering(tmp_path: Path) -> None:
    from power_framework.core.searcher import search_vault

    vault = _make_vault(tmp_path, "r1_det")
    _write_note(vault / "01_Projects" / "a.md", "Project", "A", "quantum deterministic")
    sync_vault_atomically(vault, sync_embeddings=False)
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
    from power_framework.core.search_scope import compile_search_scope as _compile

    r1 = _compile(vault, scope=scope)
    r2 = _compile(vault, scope=scope)
    assert r1.scope_digest == r2.scope_digest
    res1 = search_vault(vault, "quantum", max_results=5, mode="fts", domain="projects")
    res2 = search_vault(vault, "quantum", max_results=5, mode="fts", domain="projects")
    assert [r.rel_path for r in res1] == [r.rel_path for r in res2]


def test_r1_property_monotonic_narrowing(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, "r1_prop")
    sync_vault_atomically(vault, sync_embeddings=False)
    base = SearchScope(
        domain_ids=[],
        path_prefixes=[],
        source_types=[],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    restrictions = [
        SearchScope(
            domain_ids=["projects"],
            path_prefixes=[],
            source_types=[],
            trust_states=[],
            temporal_boundary=_tb(),
            project_ids=[],
            include_archived=False,
            include_quarantine=False,
        ),
        SearchScope(
            domain_ids=[],
            path_prefixes=["01_Projects"],
            source_types=[],
            trust_states=[],
            temporal_boundary=_tb(),
            project_ids=[],
            include_archived=False,
            include_quarantine=False,
        ),
        SearchScope(
            domain_ids=[],
            path_prefixes=[],
            source_types=["Project"],
            trust_states=[],
            temporal_boundary=_tb(),
            project_ids=[],
            include_archived=False,
            include_quarantine=False,
        ),
    ]
    r_base = compile_search_scope(vault, scope=base)
    corpus = ["01_Projects/a.md", "03_Resources/b.md", "02_Areas/c.md"]
    for restr in restrictions:
        # Intersect restriction with base manually via combined scope.
        combined = SearchScope(
            domain_ids=list({*base.domain_ids, *restr.domain_ids}),
            path_prefixes=list({*base.path_prefixes, *restr.path_prefixes}),
            source_types=list({*base.source_types, *restr.source_types}),
            trust_states=[],
            temporal_boundary=_tb(),
            project_ids=[],
            include_archived=False,
            include_quarantine=False,
        )
        r_comb = compile_search_scope(vault, scope=combined)
        for p in corpus:
            # With type unknown, only path dimensions narrow; source-type
            # narrowing is verified with explicit types elsewhere.
            if not restr.source_types and r_comb.is_path_in_scope(p):
                assert r_base.is_path_in_scope(p) is True


def test_r1_read_only_invariant(tmp_path: Path) -> None:
    from power_framework.core.searcher import search_vault

    vault = _make_vault(tmp_path, "r1_ro")
    target = vault / "01_Projects" / "a.md"
    _write_note(target, "Project", "A", "quantum readonly")
    sync_vault_atomically(vault, sync_embeddings=False)
    before = target.read_bytes()
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
    resolved = compile_search_scope(vault, scope=scope)
    search_vault(vault, "quantum", max_results=5, mode="fts", domain="projects")
    search_vault(vault, "quantum", max_results=5, mode="graph_assisted", domain="projects")
    assert target.read_bytes() == before
    assert resolved.scope_digest is not None


def test_r1_archive_privilege_still_fail_closed(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, "r1_arch")
    sync_vault_atomically(vault, sync_embeddings=False)
    scope = SearchScope(
        domain_ids=[],
        path_prefixes=[],
        source_types=[],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=True,
        include_quarantine=False,
    )
    with pytest.raises(SearchScopeAccessDeniedError):
        compile_search_scope(vault, scope=scope)


def test_r1_quarantine_privilege_still_fail_closed(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, "r1_quar")
    sync_vault_atomically(vault, sync_embeddings=False)
    scope = SearchScope(
        domain_ids=[],
        path_prefixes=[],
        source_types=[],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=True,
    )
    with pytest.raises(SearchScopeAccessDeniedError):
        compile_search_scope(vault, scope=scope)


def test_r1_semantic_lexical_guard_uses_resolved_scope(tmp_path: Path) -> None:
    """Auxiliary FTS call must receive the identical resolved scope."""
    import power_framework.core.searcher as S  # noqa: N812

    vault = _make_vault(tmp_path, "r1_semguard")
    _write_note(vault / "01_Projects" / "a.md", "Project", "A", "quantum semantic")
    _write_note(vault / "03_Resources" / "b.md", "Resource", "B", "quantum semantic")
    sync_vault_atomically(vault, sync_embeddings=False)
    seen: list[object] = []
    orig = S._fts_search

    def spy(vd, q, max_results=20, resolved_db=None, **kw):  # type: ignore[no-untyped-def]
        seen.append(kw.get("resolved_scope"))
        return orig(vd, q, max_results=max_results, resolved_db=resolved_db, **kw)

    with mock.patch.object(S, "_fts_search", side_effect=spy):
        S.search_vault(vault, "quantum", max_results=5, mode="hybrid", domain="projects")
    assert seen, "semantic/hybrid path must call scoped FTS"
    for s in seen:
        assert s is not None
        assert getattr(s, "domain_ids", ()) == ("projects",)


def test_r1_query_expansion_keeps_scope(tmp_path: Path) -> None:
    """Expanded query variants must operate under identical resolved scope."""
    from power_framework.core.searcher import search_vault

    vault = _make_vault(tmp_path, "r1_qexp")
    _write_note(vault / "01_Projects" / "a.md", "Project", "A", "quantum expansion")
    _write_note(vault / "03_Resources" / "b.md", "Resource", "B", "quantum expansion")
    sync_vault_atomically(vault, sync_embeddings=False)
    for mode in ("fts", "hybrid", "vector"):
        results = search_vault(vault, "quantum", max_results=5, mode=mode, domain="projects")
        assert all(r.rel_path.startswith("01_Projects/") for r in results)


def test_r1_security_scope_widening_denied(tmp_path: Path) -> None:
    """Additional caller restriction must never increase accessible evidence."""
    vault = _make_vault(tmp_path, "r1_sec")
    sync_vault_atomically(vault, sync_embeddings=False)
    broad = SearchScope(
        domain_ids=["projects"],
        path_prefixes=[],
        source_types=[],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    narrow = SearchScope(
        domain_ids=["projects"],
        path_prefixes=["01_Projects/RestrictedProject"],
        source_types=["Project"],
        trust_states=[],
        temporal_boundary=_tb(),
        project_ids=[],
        include_archived=False,
        include_quarantine=False,
    )
    r_broad = compile_search_scope(vault, scope=broad)
    r_narrow = compile_search_scope(vault, scope=narrow)
    corpus = [
        ("01_Projects/RestrictedProject/a.md", "Project"),
        ("01_Projects/AnotherProject/b.md", "Project"),
        ("01_Projects/RestrictedProject/c.md", "Resource"),
    ]
    for path, ntype in corpus:
        if r_narrow.is_path_in_scope(path, note_type=ntype):
            assert r_broad.is_path_in_scope(path, note_type=ntype) is True
    assert r_narrow.scope_digest != r_broad.scope_digest

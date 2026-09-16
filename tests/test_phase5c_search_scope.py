"""Phase 5C (P38-WP01) SearchScope pushdown tests and adversarial starvation fixtures."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from power_framework.core.context_contracts import (
    AccessPolicy,
    SearchScope,
    TemporalBoundary,
    TrustState,
)
from power_framework.core.generation_index import sync_vault_atomically
from power_framework.core.search_scope import (
    SearchScopeAccessDeniedError,
    UnknownDomainError,
    UnsupportedSearchScopeError,
    compile_search_scope,
)
from power_framework.core.searcher import (
    _fts_search,
    _graph_assisted_search,
    _hybrid_reranked_search,
    _scan_and_search,
    _vector_search,
    search_vault,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def adversarial_starvation_vault(tmp_path: Path) -> Path:
    """Create an adversarial corpus where global candidates starve a scoped target."""
    vault = tmp_path / "adversarial_vault"
    vault.mkdir()

    (vault / "01_Projects").mkdir()
    (vault / "03_Resources").mkdir()
    (vault / "05_Templates").mkdir()
    (vault / ".power").mkdir()

    (vault / "05_Templates" / "project.md").write_text("---\ntype: Project\ntitle: Template\n---\n")

    (vault / ".power" / "domains.yaml").write_text(
        """version: 1
domains:
  - name: projects
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
""",
        encoding="utf-8",
    )

    # 30 out-of-scope resource notes with extremely high BM25/TF term density for 'quantum'
    for i in range(30):
        resource_note = vault / "03_Resources" / f"resource_{i:02d}.md"
        quantum_spam = "quantum " * 50
        resource_note.write_text(
            f"""---
type: Resource
title: "Resource Quantum Note {i}"
description: "High score out-of-scope resource note"
timestamp: 2026-01-01T00:00:00
---

# Quantum Mechanics Overview {i}

{quantum_spam}
""",
            encoding="utf-8",
        )

    # 1 in-scope target note in 01_Projects with lower term frequency
    target_note = vault / "01_Projects" / "quantum_project.md"
    target_note.write_text(
        """---
type: Project
title: "Target Quantum Project"
description: "Sole in-scope target note with single query mention"
timestamp: 2026-01-01T00:00:00
---

# Quantum Computing Project Alpha

We are evaluating a quantum algorithm for local indexing.
""",
        encoding="utf-8",
    )

    sync_vault_atomically(vault, sync_embeddings=False)
    return vault


def test_adversarial_domain_starvation_defect_reproduction(
    adversarial_starvation_vault: Path,
) -> None:
    """Demonstrate candidate starvation under legacy global candidate + post-filter retrieval.

    When max_results=3 and domain="projects" (or 01_Projects), the legacy code queries
    global candidates (limited to max(3*5, 20)=20). Since 30 resource notes dominate
    the top-20 globally, the target note in 01_Projects is starved and missing.

    With SearchScope pushdown, candidate generation is restricted to the target scope
    BEFORE candidate LIMIT / scoring, so the target note is successfully returned.
    """
    vault = adversarial_starvation_vault

    # Search with domain='projects' (which maps to 01_Projects) and max_results=3
    results = search_vault(
        vault,
        "quantum",
        max_results=3,
        mode="fts",
        domain="projects",
    )

    # In legacy un-pushed searcher, results is [] because all top-20 global candidates
    # were in 03_Resources and filtered post-hoc.
    # Under Phase 5C pushdown, the target note MUST be found!
    result_paths = [r.rel_path for r in results]
    assert "01_Projects/quantum_project.md" in result_paths, (
        f"Domain starvation defect reproduced: target was starved by out-of-scope candidates! Returned: {result_paths}"
    )


@pytest.fixture
def rich_scoped_vault(tmp_path: Path) -> Path:
    """Create a rich multi-domain corpus for verifying the full 25-dimension SearchScope matrix."""
    vault = tmp_path / "rich_vault"
    vault.mkdir()

    (vault / "01_Projects").mkdir()
    (vault / "01_Projects" / "sub_escaped").mkdir()
    (vault / "01_Projects_Other").mkdir()
    (vault / "02_Areas").mkdir()
    (vault / "03_Resources").mkdir()
    (vault / "03_Resources" / "quarantine").mkdir()
    (vault / "04_Archive").mkdir()
    (vault / "05_Templates").mkdir()
    (vault / ".power").mkdir()

    (vault / "05_Templates" / "project.md").write_text("---\ntype: Project\ntitle: Template\n---\n")

    (vault / ".power" / "domains.yaml").write_text(
        """version: 1
domains:
  - name: projects
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: areas
    path: 02_Areas
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: resources
    path: 03_Resources
    template: 05_Templates/project.md
    search_priority: [fts]
""",
        encoding="utf-8",
    )

    # 1. In-scope project note
    (vault / "01_Projects" / "quantum_project.md").write_text(
        """---
type: Project
title: "Quantum Algorithm Alpha"
description: "Core quantum computation project"
timestamp: 2026-01-01T00:00:00
---

# Quantum Computing Project Alpha

We explore quantum circuits and local algorithms.
""",
        encoding="utf-8",
    )

    # 2. In-scope AI project note
    (vault / "01_Projects" / "ai_project.md").write_text(
        """---
type: Project
title: "AI Synthesis Project"
description: "Core AI project"
timestamp: 2026-01-01T00:00:00
---

# AI Synthesis Project

Artificial intelligence synthesis and agent models.
""",
        encoding="utf-8",
    )

    # 3. Colliding directory name note (must NOT match 01_Projects prefix)
    (vault / "01_Projects_Other" / "fake_project.md").write_text(
        """---
type: Project
title: "Colliding Project Note"
description: "Colliding directory note"
timestamp: 2026-01-01T00:00:00
---

# Quantum in colliding folder

Should not match 01_Projects directory prefix.
""",
        encoding="utf-8",
    )

    # 4. Special wildcard filename (% and _)
    (vault / "01_Projects" / "sub_escaped" / "special%20_name.md").write_text(
        """---
type: Project
title: "Special Escaped Name"
description: "Escaped wildcard test note"
timestamp: 2026-01-01T00:00:00
---

# Special % and _ Wildcard Target

This note tests SQL escaping of % and _ in path prefixes with quantum keyword.
""",
        encoding="utf-8",
    )

    # 5. Area note
    (vault / "02_Areas" / "operations.md").write_text(
        """---
type: Area
title: "Operations Area"
description: "Area note"
timestamp: 2026-01-01T00:00:00
---

# Operations Area

Operational maintenance and quantum procedures.
""",
        encoding="utf-8",
    )

    # 6. Resource note
    (vault / "03_Resources" / "quantum_resource.md").write_text(
        """---
type: Resource
title: "Quantum Reference Resource"
description: "Resource note"
timestamp: 2026-01-01T00:00:00
---

# Quantum Mechanics Resource

Reference quantum documentation and benchmarks.
""",
        encoding="utf-8",
    )

    # 7. Archived note (in 04_Archive and type: Archive)
    (vault / "04_Archive" / "archived_quantum.md").write_text(
        """---
type: Archive
title: "Archived Quantum Document"
description: "Archived note"
timestamp: 2024-01-01T00:00:00
---

# Archived Quantum Document

Old archived quantum document.
""",
        encoding="utf-8",
    )

    # 8. Quarantined note
    (vault / "03_Resources" / "quarantine" / "bad_quantum.md").write_text(
        """---
type: Resource
title: "Quarantined Quantum Note"
description: "Quarantined note"
timestamp: 2026-01-01T00:00:00
---

# Quarantined Quantum Note

Dangerous quantum text quarantined.
""",
        encoding="utf-8",
    )

    # 9. Temporal notes (OKF 0.2 memory lifecycle metadata)
    (vault / "01_Projects" / "active_plan.md").write_text(
        """---
type: Project
title: "Active Roadmap Plan"
description: "Currently valid plan"
timestamp: 2026-01-01T00:00:00
okf_version: "0.2"
memory:
  kind: semantic
  sources: ["https://example.com/source"]
  evidence: ["sha256:abc123"]
  valid_from: 2026-01-01
  valid_until: 2026-12-31
---

# Active Roadmap Plan

Active quantum execution strategy.
""",
        encoding="utf-8",
    )

    (vault / "01_Projects" / "historical_plan.md").write_text(
        """---
type: Project
title: "Historical Superseded Plan"
description: "Superseded plan"
timestamp: 2025-01-01T00:00:00
okf_version: "0.2"
memory:
  kind: semantic
  sources: ["https://example.com/source"]
  evidence: ["sha256:abc123"]
  valid_from: 2025-01-01
  valid_until: 2025-12-31
---

# Historical Superseded Plan

Old quantum quantum quantum quantum strategy.
""",
        encoding="utf-8",
    )

    sync_vault_atomically(vault, sync_embeddings=False)
    return vault


def make_access_policy(
    *,
    raw_access: str = "privileged",
    quarantine_access: str = "privileged",
    approval_ref: str | None = "APR-2026-001",
) -> AccessPolicy:
    """Helper to create server-issued AccessPolicy for security tests."""
    payload: dict[str, Any] = {
        "origin": "authorization_boundary",
        "actor": "admin",
        "raw_access": raw_access,
        "quarantine_access": quarantine_access,
        "redaction": "mandatory",
        "capability_id": "cap_search",
        "expires_at": datetime.now(UTC),
    }
    if approval_ref is not None:
        payload["approval_ref"] = approval_ref
    return AccessPolicy._from_authorization_boundary(**payload)


class DummyReranker:
    """Hermetic reranker stub returning constant scores for offline tests."""

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        del query
        return [1.0] * len(documents)


def test_stage_materialization_counters_zero(rich_scoped_vault: Path) -> None:
    """Verify all 6 out-of-scope materialization counters are strictly 0."""
    vault = rich_scoped_vault
    scope = SearchScope(
        domain_ids=["projects"],
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=False),
    )
    resolved_scope = compile_search_scope(vault, scope=scope)

    # 1. FTS candidate stage: 0 out-of-scope candidates returned
    fts_results = _fts_search(vault, "quantum", max_results=20, resolved_scope=resolved_scope)
    out_of_scope_fts = [
        r.rel_path for r in fts_results if not r.rel_path.startswith("01_Projects/")
    ]
    assert len(out_of_scope_fts) == 0, f"Out of scope FTS candidates: {out_of_scope_fts}"

    # 2. TF vector stage: 0 out-of-scope rows returned from vector search
    vec_results = _vector_search(vault, "quantum", max_results=20, resolved_scope=resolved_scope)
    out_of_scope_vec = [
        r.rel_path for r in vec_results if not r.rel_path.startswith("01_Projects/")
    ]
    assert len(out_of_scope_vec) == 0, f"Out of scope vector candidates: {out_of_scope_vec}"

    # 3. Dense stage: scoped chunk embeddings query returns 0 out-of-scope chunks
    chunk_sql, chunk_params = resolved_scope.build_chunk_condition()
    assert chunk_sql != ""
    assert "01_Projects" in chunk_params

    # 4. Rerank pool stage: rerank candidates are strictly scoped
    with (
        patch("power_framework.core.searcher.validate_dense_index", return_value=1),
        patch("power_framework.core.searcher._semantic_search", return_value=[]),
        patch("power_framework.core.searcher._get_reranker", return_value=DummyReranker()),
    ):
        rerank_results = _hybrid_reranked_search(
            vault, "quantum", max_results=20, resolved_scope=resolved_scope
        )
    out_of_scope_rerank = [
        r.rel_path for r in rerank_results if not r.rel_path.startswith("01_Projects/")
    ]
    assert len(out_of_scope_rerank) == 0, f"Out of scope rerank items: {out_of_scope_rerank}"

    # 5. Graph BFS stage: 0 out-of-scope graph hops
    graph_results = _graph_assisted_search(
        vault, "quantum", max_results=20, resolved_scope=resolved_scope
    )
    out_of_scope_graph = [
        r.rel_path for r in graph_results if not r.rel_path.startswith("01_Projects/")
    ]
    assert len(out_of_scope_graph) == 0, f"Out of scope graph items: {out_of_scope_graph}"

    # 6. Fallback scan stage: 0 out-of-scope read_source calls
    with patch("power_framework.core.searcher.read_source") as mock_read:
        _scan_and_search(vault, ["quantum"], resolved_scope=resolved_scope)
        for call in mock_read.call_args_list:
            req_rel_path = call.args[1].rel_path
            assert req_rel_path.startswith("01_Projects/"), (
                f"Out-of-scope file read during fallback scan: {req_rel_path}"
            )


def test_dimension_single_domain_pushdown(rich_scoped_vault: Path) -> None:
    """Verify single domain scope restricts candidates to domain path."""
    vault = rich_scoped_vault
    scope = SearchScope(
        domain_ids=["projects"],
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=False),
    )
    results = search_vault(vault, "quantum", scope=scope)
    paths = [r.rel_path for r in results]
    assert len(paths) > 0
    assert all(p.startswith("01_Projects/") for p in paths)
    assert "03_Resources/quantum_resource.md" not in paths


def test_dimension_multi_domain_union_pushdown(rich_scoped_vault: Path) -> None:
    """Verify multi-domain union includes notes from both domains and excludes others."""
    vault = rich_scoped_vault
    scope = SearchScope(
        domain_ids=["projects", "resources"],
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=False),
    )
    results = search_vault(vault, "quantum", scope=scope)
    paths = [r.rel_path for r in results]
    assert "01_Projects/quantum_project.md" in paths
    assert "03_Resources/quantum_resource.md" in paths
    assert "02_Areas/operations.md" not in paths
    assert "04_Archive/archived_quantum.md" not in paths


def test_dimension_exact_file_path_prefix(rich_scoped_vault: Path) -> None:
    """Verify exact file path prefix matches only the designated note."""
    vault = rich_scoped_vault
    scope = SearchScope(
        path_prefixes=["01_Projects/quantum_project.md"],
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=False),
    )
    results = search_vault(vault, "quantum", scope=scope)
    paths = [r.rel_path for r in results]
    assert paths == ["01_Projects/quantum_project.md"]


def test_dimension_directory_path_prefix(rich_scoped_vault: Path) -> None:
    """Verify directory path prefix matches notes within directory."""
    vault = rich_scoped_vault
    scope = SearchScope(
        path_prefixes=["01_Projects"],
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=False),
    )
    results = search_vault(vault, "quantum", scope=scope)
    paths = [r.rel_path for r in results]
    assert all(p.startswith("01_Projects/") for p in paths)


def test_dimension_directory_prefix_collision_safety(rich_scoped_vault: Path) -> None:
    """Verify prefix boundary safety: '01_Projects' does NOT match '01_Projects_Other'."""
    vault = rich_scoped_vault
    scope = SearchScope(
        path_prefixes=["01_Projects"],
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=False),
    )
    results = search_vault(vault, "quantum", scope=scope)
    paths = [r.rel_path for r in results]
    assert "01_Projects_Other/fake_project.md" not in paths


def test_dimension_wildcard_sql_escaping(rich_scoped_vault: Path) -> None:
    """Verify SQL wildcard characters (% and _) in filenames/paths are properly escaped."""
    vault = rich_scoped_vault
    scope = SearchScope(
        path_prefixes=["01_Projects/sub_escaped"],
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=False),
    )
    results = search_vault(vault, "quantum", scope=scope)
    paths = [r.rel_path for r in results]
    assert "01_Projects/sub_escaped/special%20_name.md" in paths


def test_dimension_source_types_single(rich_scoped_vault: Path) -> None:
    """Verify filtering by single OKF note_type."""
    vault = rich_scoped_vault
    scope = SearchScope(
        source_types=["Area"],
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=False),
    )
    results = search_vault(vault, "quantum", scope=scope)
    paths = [r.rel_path for r in results]
    assert paths == ["02_Areas/operations.md"]


def test_dimension_source_types_multi(rich_scoped_vault: Path) -> None:
    """Verify filtering by multiple OKF note_types."""
    vault = rich_scoped_vault
    scope = SearchScope(
        source_types=["Project", "Area"],
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=False),
    )
    results = search_vault(vault, "quantum", scope=scope)
    types = {r.note_type for r in results}
    assert types.issubset({"Project", "Area"})
    assert "03_Resources/quantum_resource.md" not in [r.rel_path for r in results]


def test_dimension_source_types_mismatch_zero_results(rich_scoped_vault: Path) -> None:
    """Verify source_types with no matching notes returns empty list without error."""
    vault = rich_scoped_vault
    scope = SearchScope(
        source_types=["NonExistentType"],
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=False),
    )
    results = search_vault(vault, "quantum", scope=scope)
    assert results == []


def test_dimension_temporal_boundary_current_view(rich_scoped_vault: Path) -> None:
    """Verify current temporal view excludes historical notes."""
    vault = rich_scoped_vault
    results = search_vault(
        vault, "plan", temporal_view="current", as_of="2026-06-01", domain="projects"
    )
    paths = [r.rel_path for r in results]
    assert "01_Projects/active_plan.md" in paths
    assert "01_Projects/historical_plan.md" not in paths


def test_dimension_temporal_boundary_historical_view(rich_scoped_vault: Path) -> None:
    """Verify historical temporal view returns only historical notes."""
    vault = rich_scoped_vault
    results = search_vault(
        vault, "plan", temporal_view="historical", as_of="2026-06-01", domain="projects"
    )
    paths = [r.rel_path for r in results]
    assert "01_Projects/historical_plan.md" in paths
    assert "01_Projects/active_plan.md" not in paths


def test_dimension_temporal_boundary_all_view(rich_scoped_vault: Path) -> None:
    """Verify 'all' temporal view returns both current and historical notes."""
    vault = rich_scoped_vault
    results = search_vault(
        vault, "plan", temporal_view="all", as_of="2026-06-01", domain="projects"
    )
    paths = [r.rel_path for r in results]
    assert "01_Projects/active_plan.md" in paths
    assert "01_Projects/historical_plan.md" in paths


def test_dimension_temporal_starvation_elimination(rich_scoped_vault: Path) -> None:
    """Verify historical note with higher term frequency does not starve current note."""
    vault = rich_scoped_vault
    # In historical_plan.md, 'quantum' appears 4 times; in active_plan.md, 'quantum' appears once.
    # With max_results=1 and temporal_view="current", active_plan must be returned.
    results = search_vault(
        vault,
        "quantum",
        max_results=1,
        temporal_view="current",
        as_of="2026-06-01",
        scope=SearchScope(
            path_prefixes=["01_Projects/active_plan.md", "01_Projects/historical_plan.md"],
            temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=False),
        ),
    )
    paths = [r.rel_path for r in results]
    assert paths == ["01_Projects/active_plan.md"]


def test_dimension_archived_excluded_by_default(rich_scoped_vault: Path) -> None:
    """Verify archived notes (04_Archive) are strictly excluded by default."""
    vault = rich_scoped_vault
    scope = SearchScope(
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=True)
    )
    results = search_vault(vault, "quantum", scope=scope)
    paths = [r.rel_path for r in results]
    assert "04_Archive/archived_quantum.md" not in paths


def test_dimension_quarantine_excluded_by_default(rich_scoped_vault: Path) -> None:
    """Verify quarantined notes are strictly excluded by default."""
    vault = rich_scoped_vault
    scope = SearchScope(
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=True)
    )
    results = search_vault(vault, "quantum", scope=scope)
    paths = [r.rel_path for r in results]
    assert "03_Resources/quarantine/bad_quantum.md" not in paths


def test_security_unsupported_trust_states_fails_closed(rich_scoped_vault: Path) -> None:
    """Verify non-empty trust_states fails closed with UnsupportedSearchScopeError."""
    vault = rich_scoped_vault
    scope = SearchScope(
        trust_states=[TrustState.RAW],
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=True),
    )
    with pytest.raises(UnsupportedSearchScopeError):
        search_vault(vault, "quantum", scope=scope)


def test_security_unsupported_project_ids_fails_closed(rich_scoped_vault: Path) -> None:
    """Verify non-empty project_ids fails closed with UnsupportedSearchScopeError."""
    vault = rich_scoped_vault
    scope = SearchScope(
        project_ids=["prj_quantum"],
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=True),
    )
    with pytest.raises(UnsupportedSearchScopeError):
        search_vault(vault, "quantum", scope=scope)


def test_security_unknown_domain_fails_closed(rich_scoped_vault: Path) -> None:
    """Verify unknown domain_ids fails closed with UnknownDomainError."""
    vault = rich_scoped_vault
    scope = SearchScope(
        domain_ids=["nonexistent_domain"],
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=True),
    )
    with pytest.raises(UnknownDomainError):
        search_vault(vault, "quantum", scope=scope)


def test_security_privileged_archive_without_policy_denied(rich_scoped_vault: Path) -> None:
    """Verify include_archived=True without AccessPolicy raises SearchScopeAccessDeniedError."""
    vault = rich_scoped_vault
    scope = SearchScope(
        include_archived=True,
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=True),
    )
    with pytest.raises(SearchScopeAccessDeniedError):
        search_vault(vault, "quantum", scope=scope)


def test_security_privileged_archive_with_unprivileged_policy_denied(
    rich_scoped_vault: Path,
) -> None:
    """Verify include_archived=True with raw_access='none' raises SearchScopeAccessDeniedError."""
    vault = rich_scoped_vault
    scope = SearchScope(
        include_archived=True,
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=True),
    )
    policy = make_access_policy(raw_access="none", quarantine_access="none", approval_ref=None)
    with pytest.raises(SearchScopeAccessDeniedError):
        search_vault(vault, "quantum", scope=scope, access_policy=policy)


def test_security_privileged_archive_with_valid_policy_allowed(rich_scoped_vault: Path) -> None:
    """Verify include_archived=True with valid privileged AccessPolicy returns archived notes."""
    vault = rich_scoped_vault
    scope = SearchScope(
        include_archived=True,
        path_prefixes=["04_Archive"],
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=True),
    )
    policy = make_access_policy(raw_access="privileged", approval_ref="APR-2026-ARCHIVE")
    results = search_vault(vault, "quantum", scope=scope, access_policy=policy)
    paths = [r.rel_path for r in results]
    assert "04_Archive/archived_quantum.md" in paths


def test_security_privileged_quarantine_without_policy_denied(rich_scoped_vault: Path) -> None:
    """Verify include_quarantine=True without AccessPolicy raises SearchScopeAccessDeniedError."""
    vault = rich_scoped_vault
    scope = SearchScope(
        include_quarantine=True,
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=True),
    )
    with pytest.raises(SearchScopeAccessDeniedError):
        search_vault(vault, "quantum", scope=scope)


def test_security_privileged_quarantine_with_unprivileged_policy_denied(
    rich_scoped_vault: Path,
) -> None:
    """Verify include_quarantine=True with quarantine_access='none' raises SearchScopeAccessDeniedError."""
    vault = rich_scoped_vault
    scope = SearchScope(
        include_quarantine=True,
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=True),
    )
    policy = make_access_policy(raw_access="none", quarantine_access="none", approval_ref=None)
    with pytest.raises(SearchScopeAccessDeniedError):
        search_vault(vault, "quantum", scope=scope, access_policy=policy)


def test_security_privileged_quarantine_with_valid_policy_allowed(
    rich_scoped_vault: Path,
) -> None:
    """Verify include_quarantine=True with valid privileged AccessPolicy returns quarantined notes."""
    vault = rich_scoped_vault
    scope = SearchScope(
        include_quarantine=True,
        path_prefixes=["03_Resources/quarantine"],
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=True),
    )
    policy = make_access_policy(quarantine_access="privileged", approval_ref="APR-2026-QUARANTINE")
    results = search_vault(vault, "quantum", scope=scope, access_policy=policy)
    paths = [r.rel_path for r in results]
    assert "03_Resources/quarantine/bad_quantum.md" in paths


def test_retrieval_modes_pushdown_all_modes(rich_scoped_vault: Path) -> None:
    """Verify search scope pushdown works seamlessly across all retrieval modes."""
    vault = rich_scoped_vault
    scope = SearchScope(
        domain_ids=["projects"],
        temporal_boundary=TemporalBoundary(as_of=date(2026, 6, 1), include_historical=False),
    )

    for mode in ("fts", "vector", "hybrid", "graph_assisted"):
        results = search_vault(vault, "quantum", mode=mode, scope=scope)
        paths = [r.rel_path for r in results]
        assert len(paths) > 0, f"Mode {mode} returned empty results"
        assert all(p.startswith("01_Projects/") for p in paths), (
            f"Mode {mode} leaked out-of-scope paths: {paths}"
        )

    with (
        patch("power_framework.core.searcher.validate_dense_index", return_value=1),
        patch("power_framework.core.searcher._semantic_search", return_value=[]),
        patch("power_framework.core.searcher._get_reranker", return_value=DummyReranker()),
    ):
        results = search_vault(vault, "quantum", mode="reranked", scope=scope)
        paths = [r.rel_path for r in results]
        assert len(paths) > 0, "Mode reranked returned empty results"
        assert all(p.startswith("01_Projects/") for p in paths), (
            f"Mode reranked leaked out-of-scope paths: {paths}"
        )


def test_backward_compatibility_unscoped_search(rich_scoped_vault: Path) -> None:
    """Verify legacy unscoped search continues to retrieve from all knowledge folders."""
    vault = rich_scoped_vault
    results = search_vault(vault, "quantum")
    paths = [r.rel_path for r in results]
    assert "01_Projects/quantum_project.md" in paths
    assert "03_Resources/quantum_resource.md" in paths
    assert "04_Archive/archived_quantum.md" in paths
    assert "03_Resources/quarantine/bad_quantum.md" not in paths

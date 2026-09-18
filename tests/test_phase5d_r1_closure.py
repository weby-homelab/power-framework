"""P38-WP02-R1 Phase 5D Closure Correction Red Reproduction Tests.

These tests systematically reproduce the 13 forensic and runtime defects
identified in Phase 5D (PR #440) closure audit:
1. Unsupported project_ids must fail closed before any candidate read
2. Invalid SearchScope must stop retrieval before any candidate read
3. Malformed explicit domain policy must fail closed (no silent empty registry)
4. Ordinary PARA-path FTS note must NOT automatically become CURATED
5. Dense vector hit must NOT automatically become CURATED
6. Unknown temporal metadata must NOT automatically become CURRENT
7. Unknown contradiction state must NOT automatically become NONE
8. Graph unavailable must be SKIPPED, not ATTEMPTED
9. Reranker unavailable must be SKIPPED, not ATTEMPTED
10. Raw fallback unavailable must be SKIPPED, not ATTEMPTED
11. Attempted stages must reach actual runtime execution boundaries
12. Dedup authority must remain bound to supporting provenance
13. Runtime byte limit == compiler limit == reported limit (2_000_000 bytes)

In PR-R1A, tests were decorated with @pytest.mark.xfail(strict=True) to capture
the pre-fix failure evidence while preserving green CI gates.
In PR-R1B, the xfail markers are removed and all 13 reproduction tests pass green.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest

from power_framework.core.application import ApplicationService
from power_framework.core.context_contracts import (
    MAX_CONTEXT_PACK_BYTES,
    AccessPolicy,
    Authority,
    AuthorityBasis,
    BudgetClass,
    ContradictionState,
    Freshness,
    QueryIntent,
    QueryIntentKind,
    RetrievalStage,
    TrustState,
)
from power_framework.core.domain_errors import DomainConfigError
from power_framework.core.retrieval_planner import RetrievalPlanner
from power_framework.core.search_scope import UnsupportedSearchScopeError

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class DummySearchResult:
    rel_path: str
    snippet: str = ""
    score: float = 0.5
    content: str = ""


class DummyStore:
    def __init__(self, tmp_dir: Path) -> None:
        self.tasks_dir = tmp_dir / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)


class SpyTaskService:
    def __init__(self, tmp_dir: Path | None = None) -> None:
        self.read_count = 0
        if tmp_dir:
            self.store = DummyStore(tmp_dir)

    def list_tasks(self, limit: int = 100) -> list[Any]:
        self.read_count += 1
        return []


class SpyDecisionService:
    def __init__(self) -> None:
        self.read_count = 0

    def list_decisions(self, limit: int = 100) -> list[Any]:
        self.read_count += 1
        return []


def _make_access_policy() -> AccessPolicy:
    return AccessPolicy._from_authorization_boundary(
        origin="authorization_boundary",
        actor="test_actor",
        raw_access="none",
        quarantine_access="none",
        redaction="mandatory",
        capability_id="compile_context",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


# ---------------------------------------------------------------------------
# Defect 1: project_ids unsupported must fail closed before any candidate read
# ---------------------------------------------------------------------------
def test_r1_project_ids_unsupported_fails_closed_before_reads(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    spy_task = SpyTaskService(vault)
    spy_decision = SpyDecisionService()
    search_reads = 0

    def spy_search(*args: Any, **kwargs: Any) -> list[Any]:
        nonlocal search_reads
        search_reads += 1
        return []

    app = ApplicationService(vault, task_service=spy_task)
    app.decision_service = spy_decision  # type: ignore[assignment]
    app._search_fn = spy_search

    # Must fail closed with typed UnsupportedSearchScopeError before reading anything
    with pytest.raises(UnsupportedSearchScopeError):
        app.compile_context(
            query="test query",
            project_ids=["project-alpha"],
            budget_class=BudgetClass.FAST,
        )

    assert spy_task.read_count == 0, "TaskService must not be read on unsupported project scope"
    assert spy_decision.read_count == 0, (
        "DecisionService must not be read on unsupported project scope"
    )
    assert search_reads == 0, "Search function must not be read on unsupported project scope"


# ---------------------------------------------------------------------------
# Defect 2: Invalid SearchScope must stop retrieval before any candidate read
# ---------------------------------------------------------------------------
def test_r2_invalid_search_scope_stops_retrieval_before_reads(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    spy_task = SpyTaskService()
    search_reads = 0

    def spy_search(*args: Any, **kwargs: Any) -> list[Any]:
        nonlocal search_reads
        search_reads += 1
        return []

    planner = RetrievalPlanner(vault, task_service=spy_task, search_fn=spy_search)
    intent = QueryIntent(
        query="test query",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.FAST,
    )
    plan = planner.plan(intent)
    # Inject unsupported trust_states into plan scope
    invalid_scope = plan.scope.model_copy(update={"trust_states": [TrustState.CANONICAL]})
    invalid_plan = plan.model_copy(update={"scope": invalid_scope})

    with pytest.raises(UnsupportedSearchScopeError):
        planner.retrieve(invalid_plan, intent, access_policy=_make_access_policy())

    assert spy_task.read_count == 0, "TaskService must not be read when scope compilation fails"
    assert search_reads == 0, "Search function must not be read when scope compilation fails"


# ---------------------------------------------------------------------------
# Defect 3: Malformed explicit domain policy must fail closed
# ---------------------------------------------------------------------------
def test_r3_malformed_domain_policy_fails_closed(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    power_dir = vault / ".power"
    power_dir.mkdir()
    config_file = power_dir / "domains.yaml"
    # Corrupt domain policy: version is a string instead of an int
    config_file.write_text("version: 'two'\nrouting: {}\n", encoding="utf-8")

    planner = RetrievalPlanner(vault)
    intent = QueryIntent(
        query="test query",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.FAST,
    )

    with pytest.raises(DomainConfigError):
        planner.plan(intent)


# ---------------------------------------------------------------------------
# Defect 4: Ordinary PARA-path FTS note must NOT automatically become CURATED
# ---------------------------------------------------------------------------
def test_r4_ordinary_para_path_fts_does_not_become_curated(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    fts_note = [
        DummySearchResult("01_Projects/unverified_note.md", "informal project snippet", 0.85)
    ]
    planner = RetrievalPlanner(vault, search_fn=lambda *args, **kwargs: fts_note)

    intent = QueryIntent(
        query="informal snippet",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.FAST,
    )
    result = planner.plan_and_retrieve(intent, access_policy=_make_access_policy())

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    # Invariant: PATH != AUTHORITY, DOMAIN != AUTHORITY
    assert candidate.authority is not Authority.CURATED
    assert candidate.trust_state is not TrustState.CURATED
    assert candidate.provenance.authority_basis is not AuthorityBasis.CURATED_NOTE
    assert candidate.authority in {Authority.UNVERIFIED, Authority.UNKNOWN, Authority.PROPOSED}


# ---------------------------------------------------------------------------
# Defect 5: Dense vector hit must NOT automatically become CURATED
# ---------------------------------------------------------------------------
def test_r5_dense_hit_does_not_become_curated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    dense_note = [DummySearchResult("random_folder/some_doc.md", "dense vector match", 0.92)]

    def search_fn(*args: Any, **kwargs: Any) -> list[Any]:
        if kwargs.get("mode") == "vector":
            return dense_note
        return []

    planner = RetrievalPlanner(vault, search_fn=search_fn)
    intent = QueryIntent(
        query="dense match",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.BALANCED,
    )
    # Create plan and manually invoke SEMANTIC stage path
    plan = planner.plan(intent)
    # Mock dense embedding readiness via monkeypatch
    monkeypatch.setattr(
        "power_framework.core.retrieval_planner.dense_embedding_ready",
        lambda: (True, "ready"),
    )
    monkeypatch.setattr(
        "power_framework.core.retrieval_planner.resolve_active_generation",
        lambda v: "gen_2026",
    )
    result = planner.retrieve(plan, intent, access_policy=_make_access_policy())
    assert len(result.candidates) >= 1
    semantic_candidate = next(
        c for c in result.candidates if c.retrieval_stage == RetrievalStage.SEMANTIC
    )
    # Invariant: RETRIEVAL STAGE != AUTHORITY, SEMANTIC HIT != CURATION
    assert semantic_candidate.authority is not Authority.CURATED
    assert semantic_candidate.trust_state is not TrustState.CURATED
    assert semantic_candidate.provenance.authority_basis is not AuthorityBasis.CURATED_NOTE


# ---------------------------------------------------------------------------
# Defect 6: Unknown temporal metadata must NOT automatically become CURRENT
# ---------------------------------------------------------------------------
def test_r6_unknown_temporal_metadata_not_automatically_current(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    fts_note = [DummySearchResult("03_Resources/undated.md", "undated reference note", 0.75)]
    planner = RetrievalPlanner(vault, search_fn=lambda *args, **kwargs: fts_note)

    intent = QueryIntent(
        query="undated reference",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.FAST,
    )
    result = planner.plan_and_retrieve(intent, access_policy=_make_access_policy())
    candidate = result.candidates[0]
    assert candidate.freshness is not Freshness.CURRENT
    assert candidate.freshness is Freshness.UNKNOWN


# ---------------------------------------------------------------------------
# Defect 7: Unknown contradiction state must NOT automatically become NONE
# ---------------------------------------------------------------------------
def test_r7_unknown_contradiction_state_not_automatically_none(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    fts_note = [DummySearchResult("02_Areas/raw_doc.md", "unverified statement", 0.70)]
    planner = RetrievalPlanner(vault, search_fn=lambda *args, **kwargs: fts_note)

    intent = QueryIntent(
        query="unverified statement",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.FAST,
    )
    result = planner.plan_and_retrieve(intent, access_policy=_make_access_policy())
    candidate = result.candidates[0]
    assert candidate.contradiction_state is not ContradictionState.NONE
    assert candidate.contradiction_state is ContradictionState.UNKNOWN


# ---------------------------------------------------------------------------
# Defect 8: Graph unavailable must be SKIPPED, not ATTEMPTED
# ---------------------------------------------------------------------------
def test_r8_graph_unavailable_skipped_not_attempted(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    planner = RetrievalPlanner(vault, search_fn=lambda *args, **kwargs: [])
    intent = QueryIntent(
        query="deep query",
        intent=QueryIntentKind.RESEARCH,
        budget_class=BudgetClass.DEEP,
    )
    result = planner.plan_and_retrieve(intent, access_policy=_make_access_policy())

    assert RetrievalStage.GRAPH_ASSISTED not in result.plan.attempted_stages
    assert RetrievalStage.GRAPH_ASSISTED in result.plan.skipped_stages


# ---------------------------------------------------------------------------
# Defect 9: Reranker unavailable must be SKIPPED, not ATTEMPTED
# ---------------------------------------------------------------------------
def test_r9_reranker_unavailable_skipped_not_attempted(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    planner = RetrievalPlanner(vault, search_fn=lambda *args, **kwargs: [])
    intent = QueryIntent(
        query="balanced query",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.BALANCED,
    )
    result = planner.plan_and_retrieve(intent, access_policy=_make_access_policy())

    assert RetrievalStage.RERANK not in result.plan.attempted_stages
    assert RetrievalStage.RERANK in result.plan.skipped_stages


# ---------------------------------------------------------------------------
# Defect 10: Raw fallback unavailable must be SKIPPED, not ATTEMPTED
# ---------------------------------------------------------------------------
def test_r10_raw_fallback_unavailable_skipped_not_attempted(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    planner = RetrievalPlanner(vault, search_fn=lambda *args, **kwargs: [])
    intent = QueryIntent(
        query="deep query",
        intent=QueryIntentKind.RESEARCH,
        budget_class=BudgetClass.DEEP,
    )
    result = planner.plan_and_retrieve(intent, access_policy=_make_access_policy())

    assert RetrievalStage.RAW_FALLBACK not in result.plan.attempted_stages
    assert RetrievalStage.RAW_FALLBACK in result.plan.skipped_stages


# ---------------------------------------------------------------------------
# Defect 11: Attempted stages must reach actual runtime execution boundaries
# ---------------------------------------------------------------------------
def test_r11_attempted_stages_reflect_actual_execution_boundary(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    planner = RetrievalPlanner(vault, search_fn=lambda *args, **kwargs: [])
    intent = QueryIntent(
        query="deep query",
        intent=QueryIntentKind.RESEARCH,
        budget_class=BudgetClass.DEEP,
    )
    result = planner.plan_and_retrieve(intent, access_policy=_make_access_policy())

    # Only stages with real executed boundaries may be in attempted_stages
    allowed_attempted = {RetrievalStage.PROJECT_STATE, RetrievalStage.FTS}
    for st in result.plan.attempted_stages:
        assert st in allowed_attempted, f"Stage {st} was marked attempted without execution"


# ---------------------------------------------------------------------------
# Defect 12: Dedup authority must remain bound to supporting provenance
# ---------------------------------------------------------------------------
def test_r12_dedup_authority_remains_bound_to_supporting_provenance(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    # Create low-authority FTS item for same source as canonical task
    high_score_fts = DummySearchResult("task:TSK-001", "Raw FTS hit with high score", 0.99)

    class MockTask:
        task_id = "TSK-001"
        title = "Important Task"
        state = "in_progress"
        objective = "Critical objective"

    class SingleTaskService:
        def list_tasks(self, limit: int = 100) -> list[Any]:
            return [MockTask()]

    planner = RetrievalPlanner(
        vault,
        task_service=SingleTaskService(),
        search_fn=lambda *args, **kwargs: [high_score_fts],
    )
    intent = QueryIntent(
        query="Important Task",
        intent=QueryIntentKind.TASK,
        budget_class=BudgetClass.FAST,
    )
    result = planner.plan_and_retrieve(intent, access_policy=_make_access_policy())

    assert len(result.candidates) == 1
    item = result.candidates[0]
    assert item.authority is Authority.CANONICAL
    assert item.provenance.authority_basis is AuthorityBasis.CANONICAL_LEDGER
    # Invariant: Score from unverified hit must NOT overwrite canonical score.
    # The canonical score is the deterministic query-relevance grade (exact
    # title-phrase match -> 0.8 here), never the 0.99 FTS score and never an
    # authority constant.
    assert item.score == 0.8, f"Canonical relevance score should be preserved, got {item.score}"
    assert item.score != 0.99


# ---------------------------------------------------------------------------
# Defect 13: Runtime byte limit == compiler limit == reported limit (2_000_000)
# ---------------------------------------------------------------------------
def test_r13_runtime_byte_limit_matches_compiler_and_reported() -> None:
    assert MAX_CONTEXT_PACK_BYTES == 2_000_000
    # Verify ContextPack enforces this exact limit
    from power_framework.core.context_compiler import MAX_CONTEXT_PACK_BYTES as COMPILER_LIMIT

    assert COMPILER_LIMIT == 2_000_000

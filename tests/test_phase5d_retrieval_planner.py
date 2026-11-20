"""Tests for Phase 5D: Multi-Domain RetrievalPlanner & Evidence Ordering.

Covers:
- Multi-domain routing and domain matches
- SearchScope construction and monotonicity
- Budget class profiles (FAST, BALANCED, DEEP)
- Canonical ledger integration (TaskService, DecisionService)
- Authority ordering: CANONICAL > CURATED > PROPOSED > RAW
- Enforcement of AUTHORITY_ORDER_VIOLATIONS = 0
- Cross-domain candidate deduplication and provenance merging
- Degraded fallback tracking when dense vector is unavailable
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from power_framework.core.context_contracts import (
    AccessPolicy,
    Authority,
    BudgetClass,
    BudgetProfile,
    CallerBudgetEscalationError,
    ModelLoadPolicy,
    QueryIntent,
    QueryIntentKind,
    RetrievalStage,
    TrustState,
)
from power_framework.core.decision_service import DecisionService
from power_framework.core.retrieval_planner import PlannerResult, RetrievalPlanner
from power_framework.core.search_scope import SearchScopeAccessDeniedError
from power_framework.core.task_service import TaskService

if TYPE_CHECKING:
    from pathlib import Path


def _make_test_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "planner_vault"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "01_Projects").mkdir(exist_ok=True)
    (vault / "02_Areas").mkdir(exist_ok=True)
    (vault / "03_Resources").mkdir(exist_ok=True)
    (vault / "05_Templates").mkdir(exist_ok=True)
    (vault / ".power").mkdir(exist_ok=True)
    (vault / "05_Templates" / "project.md").write_text(
        "---\ntype: Project\ntitle: Project Template\n---\n", encoding="utf-8"
    )
    (vault / "05_Templates" / "area.md").write_text(
        "---\ntype: Area\ntitle: Area Template\n---\n", encoding="utf-8"
    )
    (vault / "01_Projects" / "proj_alpha.md").write_text(
        "---\ntype: Project\ntitle: Alpha Project\n---\nAlpha project notes.",
        encoding="utf-8",
    )
    (vault / "02_Areas" / "infra.md").write_text(
        "---\ntype: Area\ntitle: Fleet Infra\n---\nFleet infrastructure area notes.",
        encoding="utf-8",
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
    template: 05_Templates/area.md
    search_priority: [fts, vector]
""",
        encoding="utf-8",
    )
    return vault


def _make_access_policy(*, raw: str = "none", quarantine: str = "none") -> AccessPolicy:
    now = datetime.now(UTC)
    data = {
        "origin": "authorization_boundary",
        "actor": "test_actor",
        "raw_access": raw,
        "quarantine_access": quarantine,
        "redaction": "mandatory",
        "capability_id": "retrieval_planner",
        "expires_at": now + timedelta(hours=1),
    }
    if raw == "privileged" or quarantine == "privileged":
        data["approval_ref"] = "approvals/appr-001.json"
    return AccessPolicy._from_authorization_boundary(**data)


class FakeSearchResult:
    def __init__(self, rel_path: str, snippet: str, score: float) -> None:
        self.rel_path = rel_path
        self.snippet = snippet
        self.score = score


def test_budget_profile_fast(tmp_path: Path) -> None:
    vault = _make_test_vault(tmp_path)
    planner = RetrievalPlanner(vault)
    intent = QueryIntent(
        query="test query",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.FAST,
    )
    policy = _make_access_policy()
    plan = planner.plan(intent, access_policy=policy)

    assert plan.budget.budget_class is BudgetClass.FAST
    assert plan.budget.max_candidates <= 10
    assert plan.budget.max_tokens <= 4_000
    assert plan.budget.model_load is ModelLoadPolicy.FORBIDDEN
    assert plan.budget.dense_allowed is False
    assert plan.budget.reranker_allowed is False
    assert plan.budget.graph_allowed is False
    assert plan.budget.raw_fallback_allowed is False
    assert RetrievalStage.FTS in plan.stages
    assert RetrievalStage.PROJECT_STATE in plan.stages
    assert RetrievalStage.SEMANTIC not in plan.stages


def test_budget_profile_balanced(tmp_path: Path) -> None:
    vault = _make_test_vault(tmp_path)
    planner = RetrievalPlanner(vault)
    intent = QueryIntent(
        query="test query",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.BALANCED,
    )
    policy = _make_access_policy()
    plan = planner.plan(intent, access_policy=policy)

    assert plan.budget.budget_class is BudgetClass.BALANCED
    assert plan.budget.max_candidates <= 25
    assert plan.budget.max_tokens <= 12_000
    assert plan.budget.dense_allowed is True
    assert plan.budget.reranker_allowed is True
    assert plan.budget.graph_allowed is False
    assert RetrievalStage.SEMANTIC in plan.stages


def test_budget_profile_deep(tmp_path: Path) -> None:
    vault = _make_test_vault(tmp_path)
    planner = RetrievalPlanner(vault)
    intent = QueryIntent(
        query="test query",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.DEEP,
    )
    policy = _make_access_policy()
    plan = planner.plan(intent, access_policy=policy)

    assert plan.budget.budget_class is BudgetClass.DEEP
    assert plan.budget.max_candidates <= 50
    assert plan.budget.max_tokens <= 30_000
    assert plan.budget.dense_allowed is True
    assert plan.budget.graph_allowed is True
    assert plan.budget.raw_fallback_allowed is True
    assert RetrievalStage.GRAPH_ASSISTED in plan.stages
    assert RetrievalStage.RAW_FALLBACK in plan.stages


def test_caller_budget_escalation_rejected(tmp_path: Path) -> None:
    vault = _make_test_vault(tmp_path)
    planner = RetrievalPlanner(vault)
    intent = QueryIntent(
        query="escalation attempt",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.FAST,
    )
    policy = _make_access_policy()
    illegal_hint = BudgetProfile(
        max_candidates=100,  # Server cap for FAST is 10
        max_tokens=20_000,  # Server cap for FAST is 4_000
        max_domains=10,
        max_graph_hops=5,
        model_load=ModelLoadPolicy.FORBIDDEN,
        numeric_default_is_hypothesis=True,
    )
    with pytest.raises(CallerBudgetEscalationError):
        planner.plan(intent, caller_hint=illegal_hint, access_policy=policy)


def test_privileged_scope_requires_privileged_policy(tmp_path: Path) -> None:
    vault = _make_test_vault(tmp_path)
    planner = RetrievalPlanner(vault)
    intent = QueryIntent(
        query="confidential search",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.FAST,
        include_archived=True,
    )
    unprivileged_policy = _make_access_policy(raw="none", quarantine="none")
    with pytest.raises(SearchScopeAccessDeniedError):
        planner.plan(intent, access_policy=unprivileged_policy)

    privileged_policy = _make_access_policy(raw="privileged", quarantine="privileged")
    plan = planner.plan(intent, access_policy=privileged_policy)
    assert plan.scope.include_archived is True


def test_multi_domain_routing_and_union(tmp_path: Path) -> None:
    vault = _make_test_vault(tmp_path)
    fake_results = [
        FakeSearchResult("01_Projects/proj_alpha.md", "Project Alpha description", 0.90),
        FakeSearchResult("02_Areas/infra.md", "Infra area maintenance notes", 0.80),
    ]

    planner = RetrievalPlanner(
        vault,
        search_fn=lambda *args, **kwargs: fake_results,
    )
    intent = QueryIntent(
        query="projects and areas status",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.FAST,
    )
    policy = _make_access_policy()
    result = planner.plan_and_retrieve(intent, access_policy=policy)

    assert isinstance(result, PlannerResult)
    assert len(result.candidates) == 2
    sources = [c.source_id for c in result.candidates]
    assert "01_Projects/proj_alpha.md" in sources
    assert "02_Areas/infra.md" in sources


def test_canonical_ledger_reader_for_task_and_decision(tmp_path: Path) -> None:
    vault = _make_test_vault(tmp_path)
    task_svc = TaskService(vault, create_vault=False)
    task = task_svc.create_task(
        task_id="TSK-001",
        title="Deploy Phase 5D Slice",
        objective="Urgent deployment",
    )

    dec_svc = DecisionService(vault, task_service=task_svc)
    dec = dec_svc.create_decision(
        decision_id="dec_001",
        task_id="TSK-001",
        title="Architecture Approved",
        description="Clean ADR 0008",
        requested_by="local",
    )

    planner = RetrievalPlanner(
        vault,
        task_service=task_svc,
        decision_service=dec_svc,
        search_fn=lambda *args, **kwargs: [],
    )

    # Search for task
    task_intent = QueryIntent(
        query="Deploy Phase 5D",
        intent=QueryIntentKind.TASK,
        budget_class=BudgetClass.FAST,
    )
    policy = _make_access_policy()
    task_result = planner.plan_and_retrieve(task_intent, access_policy=policy)

    assert len(task_result.candidates) >= 1
    task_item = task_result.candidates[0]
    assert task_item.source_id == f"task:{task.task_id}"
    assert task_item.authority is Authority.CANONICAL
    assert task_item.trust_state is TrustState.CANONICAL

    # Search for decision
    dec_intent = QueryIntent(
        query="Architecture Approved",
        intent=QueryIntentKind.DECISION,
        budget_class=BudgetClass.FAST,
    )
    dec_result = planner.plan_and_retrieve(dec_intent, access_policy=policy)
    assert len(dec_result.candidates) >= 1
    dec_item = dec_result.candidates[0]
    assert dec_item.source_id == f"decision:{dec.decision_id}"
    assert dec_item.authority is Authority.CANONICAL
    assert dec_item.trust_state is TrustState.CANONICAL


def test_authority_beats_semantic_similarity(tmp_path: Path) -> None:
    """Proves AUTHORITY > SEMANTIC SIMILARITY for authority-sensitive queries.

    Canonical task (score 0.85) MUST rank before Curated note with high score (0.99).
    """
    vault = _make_test_vault(tmp_path)
    task_svc = TaskService(vault, create_vault=False)
    task = task_svc.create_task(
        task_id="TSK-002",
        title="Critical Milestone",
        objective="Target deliverable",
    )

    # Search function returns note with score 0.99
    high_score_note = [
        FakeSearchResult("01_Projects/notes.md", "Critical Milestone informal note", 0.99)
    ]
    planner = RetrievalPlanner(
        vault,
        task_service=task_svc,
        search_fn=lambda *args, **kwargs: high_score_note,
    )

    intent = QueryIntent(
        query="Critical Milestone",
        intent=QueryIntentKind.PROJECT_STATE,
        budget_class=BudgetClass.FAST,
    )
    policy = _make_access_policy()
    result = planner.plan_and_retrieve(intent, access_policy=policy)

    assert len(result.candidates) == 2
    # Candidate 0 must be the canonical task despite lower score (0.85 vs 0.99)
    assert result.candidates[0].authority is Authority.CANONICAL
    assert result.candidates[0].source_id == f"task:{task.task_id}"
    assert result.candidates[1].authority is Authority.UNVERIFIED
    assert result.candidates[1].source_id == "01_Projects/notes.md"


def test_cross_domain_deduplication(tmp_path: Path) -> None:
    vault = _make_test_vault(tmp_path)
    # Search function returns duplicates of same file from different stage/domain
    dup_results = [
        FakeSearchResult("01_Projects/proj_alpha.md", "Snippet A", 0.70),
        FakeSearchResult("01_Projects/proj_alpha.md", "Snippet B", 0.85),
    ]
    planner = RetrievalPlanner(
        vault,
        search_fn=lambda *args, **kwargs: dup_results,
    )
    intent = QueryIntent(
        query="Alpha",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.FAST,
    )
    policy = _make_access_policy()
    result = planner.plan_and_retrieve(intent, access_policy=policy)

    assert len(result.candidates) == 1
    assert result.candidates[0].source_id == "01_Projects/proj_alpha.md"
    assert result.candidates[0].score == 0.85  # Kept higher score


def test_dense_fallback_tracking(tmp_path: Path) -> None:
    """Verifies degraded status and fallback reason when vector stage cannot execute."""
    vault = _make_test_vault(tmp_path)
    planner = RetrievalPlanner(
        vault,
        search_fn=lambda *args, **kwargs: [
            FakeSearchResult("01_Projects/proj_alpha.md", "FTS snippet", 0.75)
        ],
    )
    intent = QueryIntent(
        query="Alpha",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.BALANCED,  # Requests dense
    )
    policy = _make_access_policy()
    result = planner.plan_and_retrieve(intent, access_policy=policy)

    # In test environment without active dense generation/model, should degrade gracefully
    assert result.dense_used is False
    assert result.retrieval_status == "degraded"
    assert "fallback" in result.fallback_reason.lower()
    assert len(result.candidates) >= 1


def test_semantic_stage_dispatches_mode_semantic_not_vector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-01 regression: Stage 3 must call executable mode='semantic', never 'vector'."""
    vault = _make_test_vault(tmp_path)
    called_modes: list[str] = []

    def search_fn(*_args: object, **kwargs: object) -> list[FakeSearchResult]:
        mode = str(kwargs.get("mode", ""))
        called_modes.append(mode)
        if mode == "semantic":
            return [FakeSearchResult("01_Projects/proj_alpha.md", "Dense snippet", 0.91)]
        return []

    monkeypatch.setattr(
        "power_framework.core.retrieval_planner.dense_embedding_ready",
        lambda: (True, "ready"),
    )
    monkeypatch.setattr(
        "power_framework.core.retrieval_planner.resolve_active_generation",
        lambda _v: "gen_test",
    )

    planner = RetrievalPlanner(vault, search_fn=search_fn)
    intent = QueryIntent(
        query="Alpha",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.BALANCED,
    )
    result = planner.plan_and_retrieve(intent, access_policy=_make_access_policy())

    assert "semantic" in called_modes
    assert "vector" not in called_modes
    assert result.dense_used is True
    assert result.retrieval_status == "complete"
    assert any(c.retrieval_stage is RetrievalStage.SEMANTIC for c in result.candidates)


def test_semantic_stage_downgraded_result_marks_degraded_and_dense_used_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If search_vault downgrades semantic -> fts, planner must report degraded and dense_used=False."""
    from power_framework.core.searcher import SearchResults

    vault = _make_test_vault(tmp_path)

    def search_fn(*_args: object, **kwargs: object) -> list[FakeSearchResult]:
        if kwargs.get("mode") == "semantic":
            downgraded = FakeSearchResult("01_Projects/proj_alpha.md", "FTS fallback", 0.55)
            downgraded.actual_mode = "fts"  # type: ignore[attr-defined]
            downgraded.fallback_reason = "explicit_dense_fallback"  # type: ignore[attr-defined]
            return SearchResults(  # type: ignore[return-value]
                [downgraded],
                actual_mode="fts",
                fallback_reason="explicit_dense_fallback",
            )
        return [FakeSearchResult("01_Projects/proj_alpha.md", "FTS snippet", 0.65)]

    monkeypatch.setattr(
        "power_framework.core.retrieval_planner.dense_embedding_ready",
        lambda: (True, "ready"),
    )
    monkeypatch.setattr(
        "power_framework.core.retrieval_planner.resolve_active_generation",
        lambda _v: "gen_test",
    )

    planner = RetrievalPlanner(vault, search_fn=search_fn)
    intent = QueryIntent(
        query="Alpha",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.BALANCED,
    )
    result = planner.plan_and_retrieve(intent, access_policy=_make_access_policy())

    assert result.dense_used is False
    assert result.retrieval_status == "degraded"
    assert "explicit_dense_fallback" in result.fallback_reason
    assert all(c.retrieval_stage is not RetrievalStage.SEMANTIC for c in result.candidates)


def test_fast_profile_never_checks_or_invokes_semantic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FAST budget must never check dense readiness or invoke mode='semantic'."""
    vault = _make_test_vault(tmp_path)
    called_modes: list[str] = []

    def fail_if_called() -> tuple[bool, str]:
        raise AssertionError("FAST budget must not probe dense readiness")

    def search_fn(*_args: object, **kwargs: object) -> list[FakeSearchResult]:
        called_modes.append(str(kwargs.get("mode", "")))
        return [FakeSearchResult("01_Projects/proj_alpha.md", "FTS snippet", 0.8)]

    monkeypatch.setattr(
        "power_framework.core.retrieval_planner.dense_embedding_ready",
        fail_if_called,
    )

    planner = RetrievalPlanner(vault, search_fn=search_fn)
    intent = QueryIntent(
        query="Alpha",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.FAST,
    )
    result = planner.plan_and_retrieve(intent, access_policy=_make_access_policy())

    assert called_modes == ["fts"]
    assert result.dense_used is False
    assert result.retrieval_status == "complete"

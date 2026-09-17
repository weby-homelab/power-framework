"""Tests for Phase 5E: Shadow Benchmark Runner, Metric Formulas & Invariants.

Covers:
- Reproduction test: BM25 score preservation without artificial 0.99 clipping
- Authority priority over high BM25 semantic scores
- Retrieval metric formulas: Recall@K, MRR, MAP, nDCG@K, Context Precision
- Hard invariants: authority_order_violations == 0, query_side_writes == 0
- Source-ID mapping fidelity
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from power_framework.core.context_contracts import (
    AccessPolicy,
    Authority,
    BudgetClass,
    QueryIntent,
    QueryIntentKind,
)
from power_framework.core.retrieval_planner import RetrievalPlanner


def _make_policy() -> AccessPolicy:
    now = datetime.now(UTC)
    return AccessPolicy._from_authorization_boundary(
        origin="authorization_boundary",
        actor="benchmark_runner",
        raw_access="none",
        quarantine_access="none",
        redaction="mandatory",
        capability_id="retrieval_planner",
        expires_at=now + timedelta(hours=1),
    )


class DummySearchResult:
    def __init__(self, rel_path: str, snippet: str, score: float) -> None:
        self.rel_path = rel_path
        self.snippet = snippet
        self.score = score
        self.title = rel_path
        self.description = snippet
        self.note_type = "Project"
        self.tags: list[str] = []
        self.temporal_status = "current"


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "01_Projects").mkdir(exist_ok=True)
    (vault / "05_Templates").mkdir(exist_ok=True)
    (vault / "05_Templates" / "project.md").write_text(
        "---\ntype: Project\ntitle: Template\n---\n", encoding="utf-8"
    )
    (vault / ".power").mkdir(exist_ok=True)
    (vault / ".power" / "domains.yaml").write_text(
        "version: 1\ndomains:\n  - name: projects\n    path: 01_Projects\n    template: 05_Templates/project.md\n    search_priority: [fts]\n",
        encoding="utf-8",
    )
    return vault


def test_fts_candidate_score_preserves_bm25_ranking_without_artificial_capping(tmp_path: Path) -> None:
    """Reproduction test: BM25 scores > 1.0 must not be clipped to 0.99."""
    vault = _make_vault(tmp_path)

    # Note Z has high BM25 relevance (8.7), Note A has lower relevance (2.1)
    # If scores are clipped to 0.99, Note A outranks Note Z due to alphabetical tie-breaking.
    # When scores are preserved, Note Z outranks Note A.
    def mock_search(*args: Any, **kwargs: Any) -> list[DummySearchResult]:
        return [
            DummySearchResult("01_Projects/z_high_relevance.md", "High relevance content", 8.7),
            DummySearchResult("01_Projects/a_low_relevance.md", "Low relevance content", 2.1),
        ]

    planner = RetrievalPlanner(vault, search_fn=mock_search)
    intent = QueryIntent(
        query="relevance test",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.FAST,
    )
    policy = _make_policy()
    res = planner.retrieve(planner.plan(intent, access_policy=policy), intent, access_policy=policy)

    assert len(res.candidates) == 2
    # Winner must be z_high_relevance with its score preserved above 1.0
    first = res.candidates[0]
    second = res.candidates[1]
    assert first.source_id == "01_Projects/z_high_relevance.md"
    assert first.score > 1.0
    assert first.score == pytest.approx(8.7)
    assert second.source_id == "01_Projects/a_low_relevance.md"
    assert second.score == pytest.approx(2.1)


def test_authority_beats_semantic_similarity_even_with_high_bm25(tmp_path: Path) -> None:
    """Authority ordering invariant: Canonical ledger records outrank high BM25 notes."""
    vault = _make_vault(tmp_path)

    class MockTask:
        task_id = "TSK-001"
        title = "Canonical Task"
        state = "completed"
        objective = "Execute task"

    class MockTaskService:
        def list_tasks(self, limit: int = 10) -> list[MockTask]:
            return [MockTask()]

    def mock_search(*args: Any, **kwargs: Any) -> list[DummySearchResult]:
        return [
            DummySearchResult("01_Projects/unverified.md", "High score unverified note", 15.5),
        ]

    planner = RetrievalPlanner(vault, task_service=MockTaskService(), search_fn=mock_search)
    intent = QueryIntent(
        query="Execute task",
        intent=QueryIntentKind.TASK,
        budget_class=BudgetClass.FAST,
    )
    policy = _make_policy()
    res = planner.retrieve(planner.plan(intent, access_policy=policy), intent, access_policy=policy)

    assert len(res.candidates) == 2
    # Canonical item (score 0.85) must rank first before unverified item (score 15.5)
    assert res.candidates[0].authority is Authority.CANONICAL
    assert res.candidates[0].source_id == "task:TSK-001"
    assert res.candidates[1].authority is Authority.UNVERIFIED
    assert res.candidates[1].source_id == "01_Projects/unverified.md"
    assert res.candidates[1].score > res.candidates[0].score


def test_metric_formulas_exact() -> None:
    from scripts.benchmark_phase5e_shadow import (
        compute_average_precision,
        compute_context_precision,
        compute_ndcg,
        compute_recall_at_k,
        compute_reciprocal_rank,
        normalize_source_id,
    )

    # Source ID normalization
    assert normalize_source_id("01_Projects/corpus/p38-src-code-en.md") == "p38-src-code-en"
    assert normalize_source_id("task:p38-src-task-current.md") == "p38-src-task-current"
    assert normalize_source_id("decision:DEC-001") == "DEC-001"

    rel_set = {"doc_a", "doc_b"}

    # Recall@K
    assert compute_recall_at_k(["doc_a", "doc_c", "doc_d"], rel_set, 1) == 0.5
    assert compute_recall_at_k(["doc_a", "doc_b", "doc_d"], rel_set, 2) == 1.0
    assert compute_recall_at_k(["doc_c", "doc_d"], rel_set, 2) == 0.0

    # Reciprocal Rank (MRR)
    assert compute_reciprocal_rank(["doc_c", "doc_a", "doc_b"], rel_set) == 0.5
    assert compute_reciprocal_rank(["doc_a", "doc_b"], rel_set) == 1.0
    assert compute_reciprocal_rank(["doc_x", "doc_y"], rel_set) == 0.0

    # Average Precision (MAP)
    # Ranks 2 and 3 are hits: precision at 2 is 1/2, precision at 3 is 2/3. AP = (0.5 + 0.6667)/2 = 0.5833
    ap = compute_average_precision(["doc_x", "doc_a", "doc_b"], rel_set)
    assert ap == pytest.approx((1 / 2 + 2 / 3) / 2)

    # Context Precision
    assert compute_context_precision(["doc_a", "doc_c"], rel_set, k=2) == 0.5

    # nDCG
    grades = {"doc_a": 3.0, "doc_b": 1.0, "doc_c": 0.0}
    # Retrieved in ideal order: doc_a, doc_b
    assert compute_ndcg(["doc_a", "doc_b"], grades, 2) == pytest.approx(1.0)
    # Retrieved in reverse order: doc_b, doc_a
    dcg_rev = (2.0**1.0 - 1.0) / math.log2(2.0) + (2.0**3.0 - 1.0) / math.log2(3.0)
    idcg = (2.0**3.0 - 1.0) / math.log2(2.0) + (2.0**1.0 - 1.0) / math.log2(3.0)
    assert compute_ndcg(["doc_b", "doc_a"], grades, 2) == pytest.approx(dcg_rev / idcg)


def test_development_benchmark_execution_and_invariants(tmp_path: Path) -> None:
    """End-to-end integration test of benchmark runner on development split."""
    from scripts.benchmark_phase5e_shadow import generate_protocol_freeze, run_benchmark

    eval_corpus = Path("benchmarks/power38/retrieval_eval/v1.1").resolve()
    vault_dir = tmp_path / "bench_vault"

    results = run_benchmark(
        eval_corpus=eval_corpus,
        split="development",
        vault_dir=vault_dir,
    )

    # Hard Invariants
    invars = results["hard_invariants"]
    assert invars["authority_order_violations"] == 0
    assert invars["authority_order_violations_pass"] is True
    assert invars["query_side_writes"] == 0
    assert invars["query_side_writes_pass"] is True
    assert invars["prompt_injection_authority_escalation"] == 0
    assert invars["prompt_injection_authority_escalation_pass"] is True
    assert invars["determinism_mismatches"] == 0
    assert invars["determinism_mismatches_pass"] is True
    assert results["benchmark_metadata"]["all_hard_invariants_pass"] is True

    # Quality Gates
    shad = results["summary"]["shadow"]
    assert shad["recall_at_5"] >= 0.70
    assert shad["mrr"] >= 0.50
    assert shad["ndcg_at_10"] >= 0.60

    # Protocol Freeze verification
    freeze_out = tmp_path / "protocol_freeze.json"
    runner_path = Path("scripts/benchmark_phase5e_shadow.py").resolve()
    freeze = generate_protocol_freeze(
        eval_corpus=eval_corpus,
        runner_path=runner_path,
        output_path=freeze_out,
    )
    assert freeze_out.is_file()
    assert freeze["evaluation_corpus_revision"] == "v1.1"
    assert "runner_implementation_sha256" in freeze


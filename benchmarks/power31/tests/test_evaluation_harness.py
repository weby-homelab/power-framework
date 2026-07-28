"""Tests for the POWER 3.1 Release-Evidence Evaluation Harness (E2/E3).

Test groups:
  1. Metric computation unit tests (math/logic) — pure functions, no deps.
  2. Paired comparison unit tests (bootstrap, sign test) — fake data.
  3. RAG evaluation unit tests — fake retrieved docs + corpus.
  4. verify_evidence gate unit tests — fake evidence JSON.
  5. FTS smoke integration test — hermetic, no semantic model.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the harness module is importable
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "scripts"),
)

# ── Import the harness functions ──────────────────────────────────────────

from evaluation.run_release_evaluation import (
    compute_paired_stats,
    compute_query_metrics,
    compute_rag_aggregates,
    exact_sign_test_pvalue,
    mrr_at_k,
    ndcg_at_k,
    paired_bootstrap_ci,
    precision_at_k,
    recall_at_k,
    run_extractive_rag,
)

# Also import the verify module
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "scripts" / "evaluation"),
)
import importlib.util

verify_path = (
    Path(__file__).resolve().parent.parent / "scripts" / "evaluation" / "verify_evidence.py"
)
spec = importlib.util.spec_from_file_location("verify_evidence", str(verify_path))
verify_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_mod)


# ═════════════════════════════════════════════════════════════════════════════
#  1. Metric computation unit tests
# ═════════════════════════════════════════════════════════════════════════════


class TestNDCG:
    def test_ndcg_perfect(self):
        ret = ["a", "b", "c", "d", "e"]
        rel = {"a", "b", "c", "d", "e"}
        assert ndcg_at_k(ret, rel, 5) == 1.0

    def test_ndcg_zero(self):
        ret = ["a", "b", "c"]
        rel = {"x", "y"}
        assert ndcg_at_k(ret, rel, 3) == 0.0

    def test_ndcg_partial(self):
        ret = ["a", "x", "b", "y", "c"]
        rel = {"a", "b", "c"}
        val = ndcg_at_k(ret, rel, 5)
        assert 0 < val < 1.0

    def test_ndcg_empty_relevant(self):
        assert ndcg_at_k(["a", "b"], set(), 2) == 0.0

    def test_ndcg_empty_retrieved(self):
        assert ndcg_at_k([], {"a"}, 5) == 0.0

    def test_ndcg_k_greater_than_retrieved(self):
        ret = ["a"]
        rel = {"a"}
        assert ndcg_at_k(ret, rel, 10) == 1.0


class TestMRR:
    def test_mrr_first(self):
        assert mrr_at_k(["a", "b"], {"a"}, 10) == 1.0

    def test_mrr_second(self):
        assert mrr_at_k(["x", "a"], {"a"}, 10) == 0.5

    def test_mrr_not_found(self):
        assert mrr_at_k(["x", "y"], {"a"}, 10) == 0.0

    def test_mrr_k_limits(self):
        assert mrr_at_k(["x", "a"], {"a"}, 1) == 0.0

    def test_mrr_empty_retrieved(self):
        assert mrr_at_k([], {"a"}, 5) == 0.0


class TestRecall:
    def test_recall_perfect(self):
        assert recall_at_k(["a", "b"], {"a", "b"}, 2) == 1.0

    def test_recall_partial(self):
        assert recall_at_k(["a", "x"], {"a", "b"}, 2) == 0.5

    def test_recall_zero(self):
        assert recall_at_k(["x", "y"], {"a"}, 2) == 0.0

    def test_recall_empty_relevant(self):
        assert recall_at_k(["a"], set(), 2) == 0.0

    def test_recall_k_limits(self):
        assert recall_at_k(["a", "b", "c"], {"a"}, 1) == 1.0
        assert recall_at_k(["x", "a", "b"], {"a", "b"}, 1) == 0.0


class TestPrecision:
    def test_precision_perfect(self):
        assert precision_at_k(["a", "b"], {"a", "b"}, 2) == 1.0

    def test_precision_partial(self):
        assert precision_at_k(["a", "x"], {"a"}, 2) == 0.5

    def test_precision_zero(self):
        assert precision_at_k(["x", "y"], {"a"}, 2) == 0.0

    def test_precision_k_zero(self):
        assert precision_at_k(["a"], {"a"}, 0) == 0.0

    def test_precision_empty_retrieved(self):
        assert precision_at_k([], {"a"}, 5) == 0.0


class TestComputeQueryMetrics:
    def test_all_metrics_computed(self):
        ret = [
            {"doc_id": "a.md", "score": 0.9},
            {"doc_id": "b.md", "score": 0.5},
            {"doc_id": "c.md", "score": 0.3},
        ]
        relevant = {"a.md", "c.md"}
        metrics = compute_query_metrics(ret, relevant)
        assert metrics["ndcg@10"] > 0
        assert metrics["mrr@10"] == 1.0
        assert metrics["recall@5"] == pytest.approx(2 / 2)
        assert metrics["precision@5"] == pytest.approx(2 / 3)


# ═════════════════════════════════════════════════════════════════════════════
#  2. Paired comparison tests
# ═════════════════════════════════════════════════════════════════════════════


class TestBootstrapCI:
    def test_delta_zero_when_identical(self):
        baseline = [0.5, 0.6, 0.7]
        candidate = [0.5, 0.6, 0.7]
        res = paired_bootstrap_ci(baseline, candidate, n_resamples=100, seed=42)
        assert res["delta"] == 0.0
        assert res["ci_lower"] <= 0.0 <= res["ci_upper"]

    def test_delta_positive_when_better(self):
        baseline = [0.5, 0.6, 0.7]
        candidate = [0.8, 0.9, 1.0]
        res = paired_bootstrap_ci(baseline, candidate, n_resamples=100, seed=42)
        assert res["delta"] > 0

    def test_delta_negative_when_worse(self):
        baseline = [0.8, 0.9, 1.0]
        candidate = [0.5, 0.6, 0.7]
        res = paired_bootstrap_ci(baseline, candidate, n_resamples=100, seed=42)
        assert res["delta"] < 0

    def test_empty_lists(self):
        res = paired_bootstrap_ci([], [], n_resamples=10, seed=42)
        assert res["delta"] == 0.0

    def test_deterministic_seed(self):
        baseline = [random.random() for _ in range(20)]  # noqa: S311
        candidate = [random.random() for _ in range(20)]  # noqa: S311
        r1 = paired_bootstrap_ci(baseline, candidate, n_resamples=100, seed=42)
        r2 = paired_bootstrap_ci(baseline, candidate, n_resamples=100, seed=42)
        assert r1["delta"] == r2["delta"]
        assert r1["ci_lower"] == r2["ci_lower"]
        assert r1["ci_upper"] == r2["ci_upper"]

    def test_ci_coverage(self):
        baseline = [0.5] * 50
        candidate = [0.6] * 50
        res = paired_bootstrap_ci(baseline, candidate, n_resamples=1000, seed=42)
        assert res["ci_lower"] <= res["delta"] <= res["ci_upper"]


class TestSignTest:
    def test_sign_test_identical(self):
        p = exact_sign_test_pvalue([0.5, 0.6], [0.5, 0.6])
        assert p == 1.0

    def test_sign_test_all_positive(self):
        p = exact_sign_test_pvalue([0.5, 0.5], [0.6, 0.7])
        assert p <= 0.5

    def test_sign_test_all_negative(self):
        p = exact_sign_test_pvalue([0.6, 0.7], [0.5, 0.5])
        assert p <= 0.5

    def test_sign_test_empty(self):
        assert exact_sign_test_pvalue([], []) == 1.0

    def test_sign_test_single_tie(self):
        p = exact_sign_test_pvalue([0.5], [0.5])
        assert p == 1.0


class TestPairedStats:
    def test_paired_stats_structure(self):
        base = [{"ndcg@10": 0.5}, {"ndcg@10": 0.6}]
        cand = [{"ndcg@10": 0.7}, {"ndcg@10": 0.8}]
        res = compute_paired_stats(base, cand, metric_key="ndcg@10")
        assert res["metric"] == "ndcg@10"
        assert res["sample_size"] == 2
        assert "delta" in res
        assert "ci_lower" in res
        assert "ci_upper" in res
        assert "sign_test_p_value" in res
        assert res["candidate_mean"] > res["baseline_mean"]


# ═════════════════════════════════════════════════════════════════════════════
#  3. RAG evaluation unit tests
# ═════════════════════════════════════════════════════════════════════════════


class TestExtractiveRAG:
    def test_all_facts_found(self):
        corpus = {
            "doc1.md": "Docker multi-stage build reduces image size",
            "doc2.md": "PostgreSQL uses shared_buffers",
        }
        retrieved = [{"doc_id": "doc1.md", "score": 0.9}]
        expected = {
            "no_answer": False,
            "expected_answer": "Multi-stage build reduces size",
            "atomic_facts": ["Multi-stage build reduces image size"],
            "citation_document_ids": ["doc1.md"],
        }
        result = run_extractive_rag(retrieved, corpus, expected)
        assert result["correctness"] == 1.0
        assert result["groundedness"] == 1.0
        assert result["citation_accuracy"] == 1.0
        assert result["abstained"] is False
        assert result["answer"] is not None

    def test_some_facts_missing(self):
        corpus = {"doc1.md": "Docker multi-stage build"}
        retrieved = [{"doc_id": "doc1.md", "score": 0.9}]
        expected = {
            "no_answer": False,
            "expected_answer": "Some answer",
            "atomic_facts": ["Docker multi-stage build", "reduces image size"],
            "citation_document_ids": ["doc1.md"],
        }
        result = run_extractive_rag(retrieved, corpus, expected)
        assert result["correctness"] == 0.0
        assert result["groundedness"] == 0.5
        assert result["abstained"] is True

    def test_no_answer_abstains(self):
        expected = {
            "no_answer": True,
            "expected_answer": "",
            "atomic_facts": [],
            "citation_document_ids": [],
        }
        result = run_extractive_rag([], {}, expected)
        assert result["abstained"] is True
        assert result["correctness"] == 1.0
        assert result["groundedness"] == 1.0

    def test_distractor_sensitivity(self):
        corpus = {
            "primary.md": "BGE-M3 is the best embedding model",
            "distractor.md": "miniLM is also an embedding model",
        }
        retrieved = [{"doc_id": "primary.md", "score": 0.9}]
        expected = {
            "no_answer": False,
            "expected_answer": "BGE-M3 is best",
            "atomic_facts": ["BGE-M3 is the best embedding model"],
            "citation_document_ids": ["primary.md"],
        }
        result = run_extractive_rag(
            retrieved, corpus, expected, distractor_doc_ids={"distractor.md"}
        )
        assert result["distractor_sensitivity"] == 1.0

    def test_distractor_beats_primary(self):
        corpus = {
            "primary.md": "BGE-M3 is the best",
            "distractor.md": "miniLM is lightweight",
        }
        retrieved = [{"doc_id": "distractor.md", "score": 0.9}]
        expected = {
            "no_answer": False,
            "expected_answer": "BGE-M3 is best",
            "atomic_facts": ["BGE-M3 is the best"],
            "citation_document_ids": ["primary.md"],
        }
        result = run_extractive_rag(
            retrieved, corpus, expected, distractor_doc_ids={"distractor.md"}
        )
        assert result["distractor_sensitivity"] == 0.0

    def test_citation_accuracy_none_retrieved(self):
        corpus = {"primary.md": "content"}
        retrieved = [{"doc_id": "other.md", "score": 0.5}]
        expected = {
            "no_answer": False,
            "expected_answer": "answer",
            "atomic_facts": ["content"],
            "citation_document_ids": ["primary.md"],
        }
        result = run_extractive_rag(retrieved, corpus, expected)
        assert result["citation_accuracy"] == 0.0
        assert result["abstained"] is True


class TestRAGAggregates:
    def test_empty(self):
        assert compute_rag_aggregates([]) == {}

    def test_all_correct(self):
        results = [
            {
                "retrieval_mode": "answerable",
                "correctness": 1.0,
                "groundedness": 1.0,
                "citation_accuracy": 1.0,
                "abstained": False,
            },
            {
                "retrieval_mode": "answerable",
                "correctness": 1.0,
                "groundedness": 1.0,
                "citation_accuracy": 1.0,
                "abstained": False,
            },
        ]
        agg = compute_rag_aggregates(results)
        assert agg["mean_correctness"] == 1.0
        assert agg["abstention_rate"] == 0.0

    def test_no_answer_fp(self):
        results = [
            {
                "retrieval_mode": "no-answer",
                "correctness": 0.0,
                "groundedness": 0.0,
                "citation_accuracy": 0.0,
                "abstained": False,
            },
        ]
        agg = compute_rag_aggregates(results)
        assert agg["no_answer_false_positive_rate"] == 1.0
        assert agg["answerable_count"] == 0

    def test_mixed(self):
        results = [
            {
                "retrieval_mode": "answerable",
                "correctness": 1.0,
                "groundedness": 1.0,
                "citation_accuracy": 1.0,
                "abstained": True,
            },
            {
                "retrieval_mode": "no-answer",
                "correctness": 0.0,
                "groundedness": 0.0,
                "citation_accuracy": 0.0,
                "abstained": True,
            },
            {
                "retrieval_mode": "answerable",
                "correctness": 0.0,
                "groundedness": 0.5,
                "citation_accuracy": 0.5,
                "abstained": True,
            },
        ]
        agg = compute_rag_aggregates(results)
        assert agg["answerable_count"] == 2
        assert agg["no_answer_count"] == 1
        assert agg["mean_correctness"] == 0.5
        assert agg["no_answer_false_positive_rate"] == 0.0


# ═════════════════════════════════════════════════════════════════════════════
#  4. verify_evidence gate unit tests
# ═════════════════════════════════════════════════════════════════════════════


def _make_minimal_evidence() -> dict:
    return {
        "run_id": "run-1234abcd",
        "benchmark_version": "3.1.0",
        "timestamp": "2026-07-22T00:00:00+00:00",
        "source_date": "2026-07-22T00:00:00+00:00",
        "git_commit": "a" * 40,
        "dirty_tree": False,
        "config": {
            "baseline": {"file": "baseline", "path": "/path", "sha256": "a" * 64},
            "candidate": {"file": "candidate", "path": "/path", "sha256": "b" * 64},
        },
        "dataset": {
            "corpus_hash": "c" * 64,
            "queries_hash": "d" * 64,
            "qrels_hash": "e" * 64,
        },
        "dependency_lock_hash": None,
        "models_lock": {"hash": "a" * 64, "revision": "some-revision"},
        "python_version": "3.11.0",
        "platform": "linux",
        "hardware": {
            "cpu": "x86_64",
            "logical_cores": 4,
            "physical_cores": 4,
            "ram_gb": 16.0,
        },
        "strata": {"ua_to_ua": 50, "en_to_en": 50, "ua_to_en": 50, "en_to_ua": 50},
        "total_queries": 228,
        "baseline_mode": "fts",
        "candidate_mode": "semantic",
        "per_query_results": [],
        "aggregates": {
            "baseline": {"ndcg@10": 0.5},
            "candidate": {"ndcg@10": 0.6},
            "per_stratum": {},
            "no_answer_false_positive": {
                "baseline": 0,
                "candidate": 0,
                "total_no_answer": 20,
                "baseline_rate": 0.0,
                "candidate_rate": 0.0,
            },
        },
        "paired_stats": {
            "ndcg@10": {
                "metric": "ndcg@10",
                "sample_size": 200,
                "baseline_mean": 0.5,
                "candidate_mean": 0.6,
                "delta": 0.1,
                "ci_lower": 0.05,
                "ci_upper": 0.15,
                "ci_level": 0.95,
                "bootstrap_resamples": 10000,
                "sign_test_p_value": 0.001,
            },
        },
        "rag_metrics": {
            "baseline": {
                "answerable_count": 200,
                "no_answer_count": 20,
                "mean_correctness": 0.9,
                "mean_groundedness": 0.85,
                "mean_citation_accuracy": 0.8,
                "abstention_rate": 0.1,
                "no_answer_false_positive_rate": 0.0,
            },
            "candidate": {
                "answerable_count": 200,
                "no_answer_count": 20,
                "mean_correctness": 0.95,
                "mean_groundedness": 0.9,
                "mean_citation_accuracy": 0.85,
                "abstention_rate": 0.05,
                "no_answer_false_positive_rate": 0.0,
            },
        },
        "latency": {
            "baseline": {"p50_ms": 50, "p95_ms": 200},
            "candidate": {"p50_ms": 500, "p95_ms": 2000},
        },
        "peak_rss_mb": 500.0,
        "regression_budgets": {
            "benchmark_version": "3.1.0",
            "baseline": "baseline.yaml",
            "budgets": {
                "ndcg@10": {
                    "ua_to_ua": {
                        "max_absolute_regression": 0.05,
                        "min_absolute_improvement": None,
                    },
                    "en_to_en": {
                        "max_absolute_regression": 0.05,
                        "min_absolute_improvement": None,
                    },
                },
            },
        },
    }


class TestVerifyEvidenceSchema:
    def test_passes_valid_evidence(self):
        data = _make_minimal_evidence()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            fname = f.name
        try:
            rc = verify_mod.verify(fname)
            assert rc == 0
        finally:
            os.unlink(fname)

    def test_fails_missing_run_id(self):
        data = _make_minimal_evidence()
        del data["run_id"]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            fname = f.name
        try:
            rc = verify_mod.verify(fname)
            assert rc == 1
        finally:
            os.unlink(fname)

    def test_fails_invalid_run_id(self):
        data = _make_minimal_evidence()
        data["run_id"] = "bad-id"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            fname = f.name
        try:
            rc = verify_mod.verify(fname)
            assert rc == 1
        finally:
            os.unlink(fname)

    def test_fails_dirty_tree(self):
        data = _make_minimal_evidence()
        data["dirty_tree"] = True
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            fname = f.name
        try:
            rc = verify_mod.verify(fname)
            assert rc == 1
        finally:
            os.unlink(fname)

    def test_fails_regression_budget_violation(self):
        data = _make_minimal_evidence()
        data["paired_stats"]["ndcg@10"]["delta"] = -0.1
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            fname = f.name
        try:
            rc = verify_mod.verify(fname)
            assert rc == 1
        finally:
            os.unlink(fname)

    def test_fails_false_positive_gate(self):
        data = _make_minimal_evidence()
        data["aggregates"]["no_answer_false_positive"]["baseline_rate"] = 0.8
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            fname = f.name
        try:
            rc = verify_mod.verify(fname)
            assert rc == 1
        finally:
            os.unlink(fname)


class TestVerifyEvidenceEdgeCases:
    def test_missing_file(self):
        rc = verify_mod.verify("/nonexistent/path.json")
        assert rc == 1

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json")
            fname = f.name
        try:
            rc = verify_mod.verify(fname)
            assert rc == 1
        finally:
            os.unlink(fname)

    def test_empty_object(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            fname = f.name
        try:
            rc = verify_mod.verify(fname)
            assert rc == 1
        finally:
            os.unlink(fname)


# ═════════════════════════════════════════════════════════════════════════════
#  5. FTS smoke integration test (hermetic, no semantic model)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.bench
def test_fts_smoke_with_search_vault():
    """Hermetic FTS smoke: materialise a tiny corpus, sync FTS, run 1 query.

    Uses the real `search_vault` function in FTS mode.  No semantic model.
    Sets POWER_SEARCH_DB to an isolated temp file to not pollute the real index.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="power31_test_fts_"))
    vault_dir = tmpdir / "vault"
    vault_dir.mkdir()
    resource_dir = vault_dir / "03_Resources"
    resource_dir.mkdir()

    # Write 2 minimal OKF .md files
    doc1 = resource_dir / "doc1.md"
    doc1.write_text(
        "---\n"
        "type: Resource\n"
        'title: "Docker Multi-Stage"\n'
        'description: "Optimising Docker builds"\n'
        "tags: [docker, build]\n"
        "timestamp: 2026-07-22T00:00:00+00:00\n"
        "---\n"
        "\n"
        "Docker multi-stage build reduces the final image size."
    )

    doc2 = resource_dir / "doc2.md"
    doc2.write_text(
        "---\n"
        "type: Resource\n"
        'title: "PostgreSQL Tuning"\n'
        'description: "PostgreSQL performance settings"\n'
        "tags: [postgres, database]\n"
        "timestamp: 2026-07-22T00:00:00+00:00\n"
        "---\n"
        "\n"
        "PostgreSQL shared_buffers and work_mem tuning."
    )

    # Set isolated DB path
    db_path = tmpdir / "test_search.db"
    old_db = os.environ.get("POWER_SEARCH_DB")
    os.environ["POWER_SEARCH_DB"] = str(db_path)
    old_vault = os.environ.get("POWER_VAULT_DIR")
    os.environ["POWER_VAULT_DIR"] = str(vault_dir)

    try:
        from power_framework.core.db import _init_db
        from power_framework.core.searcher import _sync_vault_to_db, search_vault

        conn = sqlite3.connect(str(db_path), timeout=30)
        _init_db(conn)
        _sync_vault_to_db(vault_dir, conn, sync_embeddings=False)
        conn.close()

        results = search_vault(vault_dir, "Docker", max_results=5, mode="fts")
        assert len(results) >= 1, f"Docker query returned {len(results)} results"
        doc_ids = [Path(r.rel_path).name for r in results]
        assert "doc1.md" in doc_ids, f"doc1.md not found in {doc_ids}"

        results2 = search_vault(vault_dir, "PostgreSQL", max_results=5, mode="fts")
        assert len(results2) >= 1, f"PostgreSQL query returned {len(results2)} results"
        doc_ids2 = [Path(r.rel_path).name for r in results2]
        assert "doc2.md" in doc_ids2, f"doc2.md not found in {doc_ids2}"

    finally:
        if old_db is not None:
            os.environ["POWER_SEARCH_DB"] = old_db
        else:
            os.environ.pop("POWER_SEARCH_DB", None)
        if old_vault is not None:
            os.environ["POWER_VAULT_DIR"] = old_vault
        else:
            os.environ.pop("POWER_VAULT_DIR", None)
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.mark.bench
@pytest.mark.skip(reason="Semantic model not available in test env")
def test_semantic_smoke():
    """Placeholder for future semantic smoke test.  Skipped by default."""
    pass

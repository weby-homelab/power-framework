"""Hermetic regression tests for the FTS OR-vs-AND operator benchmark.

Covers: operator semantics (OR/AND/single-term/invalid env), scoped
environment isolation, ground-truth independence guard, the alpha/beta/gamma
bias demonstration, metrics, paired deltas, zero-result diagnostics,
bootstrap determinism, and an end-to-end run on a tiny synthetic corpus.

None of these tests touch a real vault, a real dataset, or a sealed holdout.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "benchmarks" / "fts_operator" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from bootstrap import paired_bootstrap_ci, win_tie_counts  # noqa: E402
from compare import compare_paired_rows, derive_conclusion  # noqa: E402
from ground_truth import (  # noqa: E402
    GroundTruthIndependenceError,
    assert_independent_provenance,
    extract_fts_terms,
    fts_operator_env,
    load_qrels,
    term_and_rule_matches,
)
from metrics import (  # noqa: E402
    first_relevant_rank,
    hit_rate_at_k,
    mrr_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from run_benchmark import _merge_pair_rows, _zero_result_diagnostics, main  # noqa: E402

OKF_HEADER = """---
type: Resource
title: "{title}"
description: "{description}"
timestamp: 2026-01-01T00:00:00
---

"""


def _write_note(vault: Path, rel_path: str, title: str, description: str, body: str) -> None:
    path = vault / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        OKF_HEADER.format(title=title, description=description) + body, encoding="utf-8"
    )


def _tiny_dataset(tmp_path: Path) -> tuple[Path, Path]:
    """Build a 4-document corpus, one query and graded qrels.

    Corpus: doc1 "alpha beta gamma", doc2 "alpha", doc3 "beta", doc4 "gamma".
    Curated qrels: doc1 grade 2, doc2 grade 1 (human-style partial-match
    relevance, NOT an all-terms rule).
    """
    dataset = tmp_path / "dataset"
    corpus = dataset / "corpus"
    corpus.mkdir(parents=True)
    _write_note(corpus, "doc1.md", "Doc one", "alpha beta gamma", "alpha beta gamma")
    _write_note(corpus, "doc2.md", "Doc two", "alpha only", "alpha")
    _write_note(corpus, "doc3.md", "Doc three", "beta only", "beta")
    _write_note(corpus, "doc4.md", "Doc four", "gamma only", "gamma")
    (dataset / "queries.jsonl").write_text(
        json.dumps(
            {
                "query_id": "Q1",
                "query": "alpha beta gamma",
                "language": "en",
                "target_language": "en",
                "stratum": "en_to_en",
                "query_class": "conceptual",
                "tags": ["topic_001"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (dataset / "qrels.synthetic.jsonl").write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {
                    "query_id": "Q1",
                    "document_id": "doc1.md",
                    "relevance": 2,
                    "distractor": False,
                },
                {
                    "query_id": "Q1",
                    "document_id": "doc2.md",
                    "relevance": 1,
                    "distractor": False,
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    provenance = tmp_path / "provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "schema_version": "power.fts-operator.gt-provenance.v1",
                "qrels_generation": {"rule": "curated for the hermetic test"},
                "independence_declaration": {
                    "not_derived_from_fts": True,
                    "not_derived_from_lexical_term_and": True,
                    "not_derived_from_or_and_operator_runs": True,
                    "human_judged": True,
                    "claim_class": "development_synthetic",
                },
            }
        ),
        encoding="utf-8",
    )
    return dataset, provenance


# ─────────────────────────────────────────────────────────────────────────────
# Operator semantics
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def synced_vault(sample_vault: Path) -> Path:
    """Trigger the canonical session-level FTS sync before direct _fts_search calls."""
    from power_framework.core.searcher import search_vault

    search_vault(sample_vault, "test", mode="fts", max_results=1)
    return sample_vault


class TestOperatorSemantics:
    def test_or_returns_partial_match_doc(
        self, synced_vault: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from power_framework.core.searcher import _fts_search

        monkeypatch.setenv("POWER_FTS_OPERATOR", "OR")
        results = _fts_search(synced_vault, "Test absent-token", max_results=20)
        assert results

    def test_and_rejects_partial_match_doc(
        self, synced_vault: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from power_framework.core.searcher import _fts_search

        monkeypatch.setenv("POWER_FTS_OPERATOR", "AND")
        results = _fts_search(synced_vault, "Test absent-token", max_results=20)
        assert results == []

    def test_and_returns_all_terms_doc(
        self, synced_vault: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from power_framework.core.searcher import _fts_search

        monkeypatch.setenv("POWER_FTS_OPERATOR", "AND")
        results = _fts_search(synced_vault, "Test Project", max_results=20)
        assert results
        assert any("TestProject" in r.rel_path for r in results)

    def test_single_term_or_equals_and(
        self, synced_vault: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from power_framework.core.searcher import _fts_search

        monkeypatch.setenv("POWER_FTS_OPERATOR", "OR")
        or_results = _fts_search(synced_vault, "Project", max_results=20)
        monkeypatch.setenv("POWER_FTS_OPERATOR", "AND")
        and_results = _fts_search(synced_vault, "Project", max_results=20)
        assert [r.rel_path for r in or_results] == [r.rel_path for r in and_results]

    def test_invalid_operator_fails_loudly(
        self, synced_vault: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from power_framework.core.searcher import _fts_search

        monkeypatch.setenv("POWER_FTS_OPERATOR", "XOR")
        with pytest.raises(ValueError, match="POWER_FTS_OPERATOR must be AND or OR"):
            _fts_search(synced_vault, "test", max_results=20)

    def test_fts_operator_env_scoped_restores(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POWER_FTS_OPERATOR", "OR")
        with fts_operator_env("AND"):
            assert os.environ["POWER_FTS_OPERATOR"] == "AND"
        assert os.environ["POWER_FTS_OPERATOR"] == "OR"

    def test_fts_operator_env_scoped_removes_when_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("POWER_FTS_OPERATOR", raising=False)
        with fts_operator_env("AND"):
            assert os.environ["POWER_FTS_OPERATOR"] == "AND"
        assert "POWER_FTS_OPERATOR" not in os.environ

    def test_no_env_leak_between_benchmark_variants(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("POWER_FTS_OPERATOR", raising=False)
        with fts_operator_env("OR"):
            pass
        with fts_operator_env("AND"):
            pass
        assert "POWER_FTS_OPERATOR" not in os.environ


# ─────────────────────────────────────────────────────────────────────────────
# Ground-truth independence guard + bias demonstration
# ─────────────────────────────────────────────────────────────────────────────


class TestGroundTruthGuard:
    def test_qrels_without_provenance_rejected(self, tmp_path: Path) -> None:
        qrels = tmp_path / "qrels.jsonl"
        qrels.write_text(
            json.dumps({"query_id": "Q1", "document_id": "d.md", "relevance": 2}) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(GroundTruthIndependenceError):
            load_qrels(qrels)

    def test_provenance_declaring_term_and_derivation_rejected(self) -> None:
        provenance = {
            "independence_declaration": {
                "not_derived_from_fts": True,
                "not_derived_from_lexical_term_and": False,
                "not_derived_from_or_and_operator_runs": True,
                "human_judged": False,
            }
        }
        with pytest.raises(GroundTruthIndependenceError, match="lexical_term_and"):
            assert_independent_provenance(provenance)

    def test_provenance_without_declaration_rejected(self) -> None:
        with pytest.raises(GroundTruthIndependenceError, match="independence_declaration"):
            assert_independent_provenance({"qrels_generation": {}})

    def test_provenance_without_human_judged_flag_rejected(self) -> None:
        provenance = {
            "independence_declaration": {
                "not_derived_from_fts": True,
                "not_derived_from_lexical_term_and": True,
                "not_derived_from_or_and_operator_runs": True,
            }
        }
        with pytest.raises(GroundTruthIndependenceError, match="human_judged"):
            assert_independent_provenance(provenance)

    def test_term_and_rule_would_mislabel_curated_relevance(self) -> None:
        corpus = {
            "docA.md": "alpha beta gamma",
            "docB.md": "alpha",
            "docC.md": "beta",
            "docD.md": "gamma",
        }
        query_terms = ["alpha", "beta", "gamma"]
        curated_qrels = {"docA.md": 3, "docB.md": 2, "docC.md": 1}
        term_and_qrels = {
            path: 1 for path, text in corpus.items() if term_and_rule_matches(query_terms, text)
        }
        assert term_and_qrels == {"docA.md": 1}
        assert set(term_and_qrels) != set(curated_qrels)
        for doc in ("docB.md", "docC.md"):
            assert doc in curated_qrels
            assert doc not in term_and_qrels


# ─────────────────────────────────────────────────────────────────────────────
# Metrics correctness
# ─────────────────────────────────────────────────────────────────────────────


class TestMetrics:
    RELEVANT: ClassVar[dict[str, int]] = {"doc1.md": 2, "doc2.md": 1, "doc3.md": 1}

    def test_ndcg_graded(self) -> None:
        retrieved = ["doc1.md", "docX.md", "doc3.md", "doc2.md", "docY.md"]
        assert 0.0 < ndcg_at_k(retrieved, self.RELEVANT, 5) < 1.0
        assert ndcg_at_k(retrieved, self.RELEVANT, 5) > ndcg_at_k(
            ["docX.md", "docY.md", "docZ.md"], self.RELEVANT, 5
        )

    def test_ndcg_perfect_ranking_is_one(self) -> None:
        retrieved = ["doc1.md", "doc2.md", "doc3.md", "docX.md"]
        assert ndcg_at_k(retrieved, self.RELEVANT, 5) == pytest.approx(1.0)

    def test_recall(self) -> None:
        assert recall_at_k(["doc1.md", "doc2.md"], self.RELEVANT, 5) == pytest.approx(2 / 3)
        assert recall_at_k(["docX.md"], self.RELEVANT, 5) == pytest.approx(0.0)
        assert recall_at_k(["doc1.md"], {}, 5) == pytest.approx(0.0)

    def test_mrr(self) -> None:
        assert mrr_at_k(["docX.md", "doc2.md"], self.RELEVANT, 5) == pytest.approx(0.5)
        assert mrr_at_k(["docX.md", "docY.md"], self.RELEVANT, 5) == pytest.approx(0.0)

    def test_precision_and_hit_rate(self) -> None:
        assert precision_at_k(["doc1.md", "docX.md", "doc2.md"], self.RELEVANT, 5) == pytest.approx(
            2 / 3
        )
        assert hit_rate_at_k(["docX.md", "doc2.md"], self.RELEVANT, 5) == pytest.approx(1.0)
        assert hit_rate_at_k(["docX.md"], self.RELEVANT, 5) == pytest.approx(0.0)

    def test_first_relevant_rank(self) -> None:
        assert first_relevant_rank(["docX.md", "doc2.md"], self.RELEVANT) == 2
        assert first_relevant_rank(["docX.md"], self.RELEVANT) is None


# ─────────────────────────────────────────────────────────────────────────────
# Paired comparison, deltas, zero-result, bootstrap
# ─────────────────────────────────────────────────────────────────────────────


class TestPairedComparison:
    def _rows(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        or_rows = [
            {
                "query_id": "Q1",
                "query": "alpha beta gamma",
                "query_language": "en",
                "query_class": "conceptual",
                "stratum": "en_to_en",
                "query_term_count": 3,
                "relevant_count": 2,
                "result_count": 4,
                "ndcg@5": 0.8,
                "ndcg@10": 0.8,
                "recall@5": 0.5,
                "recall@10": 1.0,
                "mrr@5": 1.0,
                "mrr@10": 1.0,
                "precision@5": 0.4,
                "precision@10": 0.2,
                "hit_rate@5": 1.0,
                "hit_rate@10": 1.0,
                "relevant_hits@5": 1,
                "relevant_hits@10": 2,
                "first_relevant_rank": 1.0,
                "zero_result": 0.0,
                "or_top10": "[]",
                "or_only_relevant": '["doc1.md"]',
            },
        ]
        and_rows = [
            {
                "query_id": "Q1",
                "query": "alpha beta gamma",
                "query_language": "en",
                "query_class": "conceptual",
                "stratum": "en_to_en",
                "query_term_count": 3,
                "relevant_count": 2,
                "result_count": 1,
                "ndcg@5": 1.0,
                "ndcg@10": 1.0,
                "recall@5": 0.5,
                "recall@10": 0.5,
                "mrr@5": 1.0,
                "mrr@10": 1.0,
                "precision@5": 1.0,
                "precision@10": 1.0,
                "hit_rate@5": 1.0,
                "hit_rate@10": 1.0,
                "relevant_hits@5": 1,
                "relevant_hits@10": 1,
                "first_relevant_rank": 1.0,
                "zero_result": 0.0,
                "and_top10": "[]",
                "and_only_relevant": '["doc1.md"]',
            },
        ]
        return or_rows, and_rows

    def test_pair_rows_matched(self) -> None:
        or_rows, and_rows = self._rows()
        merged = _merge_pair_rows(or_rows, and_rows)
        assert len(merged) == 1
        assert merged[0]["query_id"] == "Q1"
        assert merged[0]["or_result_count"] == 4
        assert merged[0]["and_result_count"] == 1

    def test_pair_rows_missing_and_query_raises(self) -> None:
        or_rows, _ = self._rows()
        with pytest.raises(ValueError, match="paired design violated"):
            _merge_pair_rows(or_rows, [])

    def test_delta_calculation(self) -> None:
        or_rows, and_rows = self._rows()
        comparison = compare_paired_rows(or_rows, and_rows, seed=20260801, n_resamples=1000)
        recall = comparison["metrics"]["recall@10"]
        assert recall["delta_and_minus_or"] == pytest.approx(-0.5)
        assert recall["or_wins"] == 1
        assert recall["and_wins"] == 0
        assert recall["ties"] == 0
        assert comparison["metrics"]["ndcg@5"]["delta_and_minus_or"] == pytest.approx(0.2)

    def test_zero_result_diagnostics(self) -> None:
        or_rows, and_rows = self._rows()
        or_rows[0]["zero_result"] = 0.0
        and_rows[0]["zero_result"] = 1.0
        and_rows[0]["result_count"] = 0
        merged = _merge_pair_rows(or_rows, and_rows)
        lost = _zero_result_diagnostics(merged)
        assert len(lost) == 1
        assert lost[0]["query_id"] == "Q1"

    def test_win_tie_counts(self) -> None:
        assert win_tie_counts([1.0, 0.5, 0.5], [0.5, 0.5, 0.5]) == {
            "and_wins": 1,
            "or_wins": 0,
            "ties": 2,
        }

    def test_bootstrap_deterministic_with_seed(self) -> None:
        and_scores = [0.8, 0.6, 0.7, 0.5, 0.9, 0.4, 0.6, 0.3]
        or_scores = [0.7, 0.5, 0.6, 0.5, 0.8, 0.4, 0.5, 0.3]
        first = paired_bootstrap_ci(and_scores, or_scores, n_resamples=10_000, seed=42)
        second = paired_bootstrap_ci(and_scores, or_scores, n_resamples=10_000, seed=42)
        assert first == second
        assert first["ci_lower"] is not None
        assert first["ci_upper"] is not None
        assert first["ci_lower"] <= first["mean_delta"] <= first["ci_upper"]

    def test_bootstrap_empty_sample_reports_no_ci(self) -> None:
        result = paired_bootstrap_ci([], [], n_resamples=1000, seed=42)
        assert result["ci_lower"] is None
        assert result["ci_upper"] is None
        assert result["n"] == 0

    def test_bootstrap_unequal_samples_rejected(self) -> None:
        with pytest.raises(ValueError, match="equal per-query sample sizes"):
            paired_bootstrap_ci([1.0, 2.0], [1.0], n_resamples=100, seed=42)

    def test_insufficient_sample_conclusion(self) -> None:
        or_rows, and_rows = self._rows()
        comparison = compare_paired_rows(or_rows, and_rows, seed=42, n_resamples=100)
        assert comparison["conclusion"]["label"] == "insufficient evidence"

    def test_conclusion_blocks_and_on_zero_result_penalty(self) -> None:
        comparison = {
            "ndcg@5": {"delta_and_minus_or": 0.05},
            "recall@10": {"delta_and_minus_or": 0.05},
            "mrr@5": {"delta_and_minus_or": 0.05},
            "zero_result": {"delta_and_minus_or": 0.10},
        }
        conclusion = derive_conclusion(comparison, sample_size=50)
        assert conclusion["label"] == "no clear winner"
        assert "blocked" in conclusion["rationale"]

    def test_conclusion_prefers_or_when_or_leads(self) -> None:
        comparison = {
            "ndcg@5": {"delta_and_minus_or": -0.05},
            "recall@10": {"delta_and_minus_or": -0.05},
            "mrr@5": {"delta_and_minus_or": -0.05},
            "zero_result": {"delta_and_minus_or": -0.05},
        }
        assert derive_conclusion(comparison, sample_size=50)["label"] == "OR preferred"

    def test_conclusion_prefers_and_when_and_leads_cleanly(self) -> None:
        comparison = {
            "ndcg@5": {"delta_and_minus_or": 0.05},
            "recall@10": {"delta_and_minus_or": 0.05},
            "mrr@5": {"delta_and_minus_or": 0.05},
            "zero_result": {"delta_and_minus_or": -0.05},
        }
        assert derive_conclusion(comparison, sample_size=50)["label"] == "AND preferred"


# ─────────────────────────────────────────────────────────────────────────────
# Query preprocessing mirror + end-to-end hermetic run
# ─────────────────────────────────────────────────────────────────────────────


class TestQueryClassification:
    def test_phrase_and_hyphen_and_stopwords(self) -> None:
        terms = extract_fts_terms('"exact phrase" foo-bar the to')
        assert '"exact phrase"' in terms
        assert any(t == '"foo-bar"' for t in terms)
        assert "the*" not in terms
        assert "to*" not in terms

    def test_ukrainian_words_kept(self) -> None:
        terms = extract_fts_terms("резервне копіювання для мережі")
        assert "резервне*" in terms
        assert "копіювання*" in terms
        assert "для*" not in terms

    def test_cyrillic_classified_as_uk(self) -> None:
        from ground_truth import classify_query

        record = classify_query("Q1", {"query": "як налаштувати Docker", "stratum": "ua_to_en"})
        assert record.language == "uk"
        assert record.stratum == "ua_to_en"
        record_en = classify_query("Q2", {"query": "how to deploy k3s", "stratum": "en_to_ua"})
        assert record_en.language == "en"
        assert record_en.term_count == 3


class TestEndToEndHermeticRun:
    def test_run_produces_all_artifacts(self, tmp_path: Path) -> None:
        dataset, provenance = _tiny_dataset(tmp_path)
        output = tmp_path / "results"
        assert (
            main(
                [
                    "--dataset",
                    str(dataset),
                    "--provenance",
                    str(provenance),
                    "--output",
                    str(output),
                    "--samples",
                    "100",
                ]
            )
            == 0
        )
        for name in (
            "manifest.json",
            "per_query.csv",
            "summary.csv",
            "comparison.json",
            "comparison.md",
            "bootstrap.json",
            "failures.json",
        ):
            assert (output / name).is_file(), name

        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["variants"]["fts_or"]["fts_operator"] == "OR"
        assert manifest["variants"]["fts_and"]["fts_operator"] == "AND"
        assert manifest["code_changed_between_variants"] is False
        assert manifest["bm25_weights"]["title"] == 10.0
        assert manifest["git_commit"]
        assert manifest["queries_sha256"]
        assert manifest["qrels_sha256"]

        comparison = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
        assert comparison["metrics"]["recall@10"]["or_mean"] == pytest.approx(1.0)
        assert comparison["metrics"]["recall@10"]["and_mean"] == pytest.approx(0.5)
        assert comparison["metrics"]["recall@10"]["delta_and_minus_or"] == pytest.approx(-0.5)

        csv_text = (output / "per_query.csv").read_text(encoding="utf-8")
        assert "query_id" in csv_text
        assert "or_result_count" in csv_text
        assert "and_result_count" in csv_text
        assert "or_only_relevant" in csv_text
        assert "common_relevant" in csv_text

    def test_run_rejects_missing_provenance_fixture(self, tmp_path: Path) -> None:
        dataset, _ = _tiny_dataset(tmp_path)
        output = tmp_path / "results2"
        with pytest.raises(SystemExit, match="missing required fixture"):
            main(
                [
                    "--dataset",
                    str(dataset),
                    "--provenance",
                    str(tmp_path / "missing-provenance.json"),
                    "--output",
                    str(output),
                    "--samples",
                    "100",
                ]
            )

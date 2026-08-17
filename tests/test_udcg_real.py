from __future__ import annotations

import math

import pytest

from power_framework.core.metrics.udcg_real import (
    SEMANTIC_GT_PATH,
    _load_semantic_gt,
    compute_ndcg,
    compute_semantic_udcg,
    dcg_at_k,
    ndcg_at_k,
)


class TestDcgAtK:
    def test_empty_returns_zero(self):
        assert dcg_at_k([], k=5) == 0.0

    def test_basic_dcg_value(self):
        result = dcg_at_k([3], k=1)
        expected = (2**3 - 1) / math.log2(2)
        assert result == pytest.approx(expected)

    def test_multiple_ranks(self):
        result = dcg_at_k([3, 2, 1], k=3)
        ideal = dcg_at_k([3, 2, 1], k=3)
        assert result > 0.0
        assert result == ideal  # computed once

    def test_dcg_penalizes_lower_rank(self):
        good_first = dcg_at_k([3, 0, 0], k=3)
        bad_first = dcg_at_k([0, 3, 0], k=3)
        assert good_first > bad_first

    def test_k_truncation(self):
        full = dcg_at_k([3, 2, 1], k=5)
        truncated = dcg_at_k([3, 2, 1], k=2)
        assert truncated < full


class TestNdcgAtK:
    def test_empty_returns_zero(self):
        assert ndcg_at_k([], k=5) == 0.0

    def test_perfect_ranking_is_one(self):
        assert ndcg_at_k([3, 2, 1], k=3) == pytest.approx(1.0)

    def test_imperfect_ranking_less_than_one(self):
        good = ndcg_at_k([3, 2, 1], k=3)
        bad = ndcg_at_k([0, 3, 1], k=3)
        assert bad < good
        assert bad < 1.0

    def test_all_zero_relevance(self):
        assert ndcg_at_k([0, 0, 0], k=3) == 0.0

    def test_single_relevant_doc_at_top(self):
        assert ndcg_at_k([3], k=1) == pytest.approx(1.0)

    def test_single_relevant_doc_at_rank_two(self):
        ndcg = ndcg_at_k([0, 3], k=2)
        assert ndcg < 1.0
        assert ndcg > 0.0


class TestComputeNdcg:
    def test_perfect_run(self):
        qrels = {"q1": {"doc_a": 3, "doc_b": 2}}
        run = {"q1": {"doc_a": 0.9, "doc_b": 0.8}}
        result = compute_ndcg(qrels, run, k=2)
        assert result["ndcg@2"] == pytest.approx(1.0)

    def test_imperfect_run(self):
        qrels = {"q1": {"doc_a": 3, "doc_b": 2}}
        run = {"q1": {"doc_b": 0.8, "doc_a": 0.9}}  # wrong order
        result = compute_ndcg(qrels, run, k=2)
        assert result["ndcg@2"] < 1.0

    def test_missing_doc_is_zero_relevance(self):
        qrels = {"q1": {"doc_a": 3}}
        run = {"q1": {"doc_unknown": 0.9, "doc_a": 0.8}}
        result = compute_ndcg(qrels, run, k=2)
        assert result["ndcg@2"] < 1.0
        assert result["ndcg@2"] > 0.0

    def test_empty_qrels_returns_zero(self):
        result = compute_ndcg({}, {}, k=5)
        assert result["ndcg@5"] == 0.0

    def test_multiple_queries_averaged(self):
        qrels = {
            "q1": {"doc_a": 3},
            "q2": {"doc_b": 2},
        }
        run = {
            "q1": {"doc_a": 0.9},
            "q2": {"doc_b": 0.9},
        }
        result = compute_ndcg(qrels, run, k=1)
        assert result["ndcg@1"] == pytest.approx(1.0)


class TestLoadSemanticGt:
    def test_loads_semantic_gt_file(self):
        qrels = _load_semantic_gt(SEMANTIC_GT_PATH)
        assert isinstance(qrels, dict)
        assert len(qrels) > 0
        for query, doc_grades in qrels.items():
            assert isinstance(query, str)
            for doc, grade in doc_grades.items():
                assert isinstance(doc, str)
                assert isinstance(grade, int)
                assert 0 <= grade <= 3

    def test_all_queries_have_at_least_one_relevant(self):
        qrels = _load_semantic_gt(SEMANTIC_GT_PATH)
        for query, doc_grades in qrels.items():
            assert len(doc_grades) >= 1, f"Query {query!r} has no relevant docs"

    def test_includes_bilingual_queries(self):
        qrels = _load_semantic_gt(SEMANTIC_GT_PATH)
        ua_queries = [q for q in qrels if any(ord(c) > 0x0400 for c in q)]
        assert len(ua_queries) > 0, "No Ukrainian queries found in semantic GT"
        en_queries = [q for q in qrels if all(ord(c) < 0x0400 or ord(c) > 0x04FF for c in q)]
        assert len(en_queries) > 0, "No English queries found in semantic GT"


class TestComputeSemanticUdcg:
    def test_uses_real_gt_and_returns_valid(self):
        run = {
            "how to verify gpg commit signature before merge": {
                "06_Daily_Logs/MASTER-LESSONS-LEARNED.md": 0.95,
                "PROTOCOLS/Successor-Hub.md": 0.8,
            },
            "безпека сервера фаєрвол nftables налаштування": {
                "02_Areas/Infrastructure/Security.md": 0.9,
                "02_Areas/Infrastructure/PROD_Safety_Mandate.md": 0.7,
            },
        }
        result = compute_semantic_udcg(run, k=5)
        assert result["ndcg@5"] > 0.0
        assert result["ndcg@5"] <= 1.0
        assert result["udcg@5"] == pytest.approx(result["ndcg@5"])

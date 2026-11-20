"""Tests for Phase 5E Living Retrieval Regression Benchmark."""

from __future__ import annotations

from typing import Any

import pytest

from scripts.run_living_benchmark import (
    DEFAULT_DATASET_DIR,
    load_dataset,
    run_living_benchmark,
)


def _assert_all_invariants_zero(mode_report: dict[str, Any]) -> None:
    assert mode_report["all_invariants_zero"] is True, mode_report["invariants"]
    for key, val in mode_report["invariants"].items():
        assert val == 0, f"Expected invariant {key} == 0, got {val}"


def test_living_dataset_integrity() -> None:
    """Dataset is complete, anonymized, covers core/daily/semantic/security and UA/EN/MIXED."""
    canonical, lexicon, queries = load_dataset(DEFAULT_DATASET_DIR)

    assert len(queries) >= 30
    groups = {str(q["group"]) for q in queries}
    assert {"core", "daily_work", "semantic_paraphrase", "security"} <= groups
    languages = {str(q["language"]) for q in queries}
    assert {"UA", "EN", "MIXED"} <= languages

    clusters = lexicon.get("clusters", {})
    assert len(clusters) >= 15
    assert int(lexicon.get("dimension", 0)) == 1024

    canonical_ids = (
        {f"task:{t['task_id']}" for t in canonical.get("tasks", [])}
        | {f"decision:{d['decision_id']}" for d in canonical.get("decisions", [])}
        | {f"project:{p['project_id']}" for p in canonical.get("projects", [])}
    )
    corpus_dir = DEFAULT_DATASET_DIR / "corpus"

    for q in queries:
        refs = [
            *q.get("expected_relevant", []),
            *q.get("expected_exclusions", []),
            *(
                [q["expected_authority_winner"]]
                if q.get("expected_authority_winner") is not None
                else []
            ),
        ]
        for ref in refs:
            ref_str = str(ref)
            if ref_str.startswith(("task:", "decision:", "project:")):
                assert ref_str in canonical_ids, f"Missing canonical fixture {ref_str}"
            else:
                assert (corpus_dir / ref_str).is_file(), f"Missing corpus note {ref_str}"


def test_living_benchmark_fast_mode_invariants_and_quality() -> None:
    """FAST lexical + canonical mode passes all hard invariants and baseline recall floors."""
    report = run_living_benchmark(
        DEFAULT_DATASET_DIR,
        modes=("FAST",),
        embedder_mode="hermetic",
    )
    fast = report["modes"]["FAST"]
    _assert_all_invariants_zero(fast)

    summary = fast["summary"]
    assert summary["dense_used_count"] == 0
    assert summary["recall_at_5"] >= 0.55
    assert summary["mrr"] >= 0.50
    assert summary["ndcg_at_10"] >= 0.55
    assert fast["by_group"]["core"]["recall_at_5"] >= 0.80


def test_living_benchmark_balanced_real_dense_beats_fast_on_semantic_paraphrases() -> None:
    """BALANCED executes real Stage 3 dense search, preserves invariants, and beats FAST on paraphrases."""
    pytest.importorskip("numpy")

    report = run_living_benchmark(
        DEFAULT_DATASET_DIR,
        modes=("FAST", "BALANCED"),
        embedder_mode="hermetic",
    )
    fast = report["modes"]["FAST"]
    balanced = report["modes"]["BALANCED"]

    _assert_all_invariants_zero(fast)
    _assert_all_invariants_zero(balanced)

    bal_summary = balanced["summary"]
    fast_summary = fast["summary"]
    assert bal_summary["dense_used_count"] == report["query_count"]
    assert bal_summary["degraded_count"] == 0
    assert bal_summary["recall_at_5"] >= 0.85
    assert bal_summary["mrr"] >= 0.80
    assert bal_summary["ndcg_at_10"] >= 0.85
    assert bal_summary["recall_at_5"] >= fast_summary["recall_at_5"]

    fast_sem = fast["by_group"]["semantic_paraphrase"]["recall_at_5"]
    bal_sem = balanced["by_group"]["semantic_paraphrase"]["recall_at_5"]
    assert bal_sem > fast_sem
    assert bal_sem >= 0.85

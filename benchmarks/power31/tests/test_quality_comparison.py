"""Hermetic tests for the semantic-vs-reranked comparison harness."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from evaluation.run_quality_comparison import (  # noqa: E402
    CORPUS_DIR,
    MANIFEST_FILE,
    _hash_dataset,
    percentile,
    ranking_metrics,
)


def test_percentile_is_deterministic_nearest_rank() -> None:
    values = [9.0, 1.0, 5.0, 3.0, 7.0]
    assert percentile(values, 50) == 5.0
    assert percentile(values, 95) == 9.0
    assert percentile([], 95) == 0.0


def test_ranking_metrics_are_bounded_and_exact() -> None:
    metrics = ranking_metrics(["primary.md", "other.md"], {"primary.md"})
    assert metrics == {"ndcg@10": 1.0, "mrr@10": 1.0, "recall@10": 1.0}
    assert ranking_metrics(["other.md"], {"primary.md"}) == {
        "ndcg@10": 0.0,
        "mrr@10": 0.0,
        "recall@10": 0.0,
    }


def test_canonical_dataset_fingerprint_matches_manifest() -> None:
    manifest = json.loads(Path(MANIFEST_FILE).read_text(encoding="utf-8"))
    result = _hash_dataset(manifest)
    assert result["queries_count"] == 228
    assert result["qrels_count"] == 416
    assert result["corpus_count"] == len(list(Path(CORPUS_DIR).glob("*.md"))) == 100
    assert result["queries_hash"] == manifest["queries"]["hash_sha256"]
    assert result["qrels_hash"] == manifest["qrels"]["hash_sha256"]

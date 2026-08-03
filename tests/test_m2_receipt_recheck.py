"""Tests for transparent threshold-only M2 receipt readback."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = (
    Path(__file__).parents[1]
    / "benchmarks"
    / "human_retrieval"
    / "scripts"
    / "recheck_development_receipt.py"
)
SPEC = importlib.util.spec_from_file_location("m2_recheck", SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _receipt() -> dict[str, object]:
    aggregate = {
        "recall_at_10": {"value": 0.75},
        "ndcg_at_10": {"value": 0.9},
        "mrr_at_10": {"value": 0.8},
        "citation_provenance_accuracy": {"value": 1.0},
        "abstention_quality": {"value": 1.0},
        "p95_latency_ms": {"value": 100.0},
        "stale_answer_rate": {"value": 0.0},
    }
    return {
        "status": "completed",
        "split": "development",
        "thresholds": {
            "recall_at_10": 0.8,
            "ndcg_at_10": 0.7,
            "mrr_at_10": 0.7,
            "citation_provenance_accuracy": 0.95,
            "stale_answer_rate_max": 0.02,
            "abstention_quality": 0.9,
            "p95_latency_ms": 1500.0,
        },
        "unavailable_modes": [],
        "evidence_contract_errors": [],
        "modes": {
            mode: {"status": "completed", "aggregate": aggregate}
            for mode in ("lexical", "semantic", "hybrid", "reranked", "graph_assisted")
        },
    }


def test_recheck_lowers_only_effective_threshold_and_keeps_sealed_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    output = tmp_path / "recheck.json"
    source.write_text(json.dumps(_receipt()), encoding="utf-8")

    result = MODULE.recheck_receipt(source, output, recall_threshold=0.75)

    assert result["quality_gate"] == "PASS"
    assert result["failed_thresholds"] == []
    assert result["threshold_profile"]["original_thresholds"]["recall_at_10"] == 0.8
    assert result["threshold_profile"]["effective_thresholds"]["recall_at_10"] == 0.75
    assert result["sealed_holdout_decision"]["decision"] == "do_not_open"

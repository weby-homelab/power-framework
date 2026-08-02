"""Focused contracts for the M2 development retrieval evaluator."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parents[1]
    / "benchmarks"
    / "human_retrieval"
    / "scripts"
    / "evaluate_retrieval.py"
)
SPEC = importlib.util.spec_from_file_location("m2_retrieval_evaluator", SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _rows(*, current_citation: bool = True) -> list[dict[str, object]]:
    return [
        {
            "query_id": "q-current",
            "document_id": "doc-current",
            "final": {
                "relevance": 2,
                "acceptable_citation": current_citation,
                "temporal_status": "current",
                "abstention_correct": "no",
                "taxonomy": "current_fact",
            },
        },
        {
            "query_id": "q-current",
            "document_id": "doc-history",
            "final": {
                "relevance": 2,
                "acceptable_citation": not current_citation,
                "temporal_status": "historical",
                "abstention_correct": "no",
                "taxonomy": "current_fact",
            },
        },
        {
            "query_id": "q-abstain",
            "document_id": "doc-current",
            "final": {
                "relevance": 0,
                "acceptable_citation": False,
                "temporal_status": "not_applicable",
                "abstention_correct": "yes",
                "taxonomy": "abstention",
            },
        },
    ]


def test_abstention_query_is_excluded_from_citation_denominator() -> None:
    qrels = MODULE.group_qrels(_rows())

    metrics = MODULE.result_metrics(
        {"query_id": "q-abstain", "journey": "abstention"},
        ["doc-current"],
        qrels["q-abstain"],
    )

    assert metrics["citation_provenance_accuracy"] is None
    assert metrics["abstention_quality"] == 1.0


def test_unjudged_top_result_is_not_dropped_before_scoring() -> None:
    qrels = MODULE.group_qrels(_rows())

    metrics = MODULE.result_metrics(
        {"query_id": "q-current", "journey": "current_fact"},
        ["outside-frozen-pool", "doc-current"],
        qrels["q-current"],
    )

    assert metrics["result_doc_ids"] == ["outside-frozen-pool", "doc-current"]
    assert metrics["citation_provenance_accuracy"] == 0.0
    assert metrics["abstention_quality"] == 0.0


def test_annotation_protocol_is_derived_from_frozen_qrel_fields() -> None:
    assert MODULE.annotation_protocol_version(_rows()) == "1.0"
    v2_rows = _rows()
    for row in v2_rows:
        final = row["final"]
        final["query_abstention_correct"] = final.pop("abstention_correct")  # type: ignore[union-attr]
    assert MODULE.annotation_protocol_version(v2_rows) == "2.0"


def test_v2_group_qrels_rejects_string_citation_and_legacy_fields() -> None:
    rows = [
        {
            "query_id": "q",
            "document_id": "doc",
            "final": {
                "relevance": 2,
                "acceptable_citation": "false",
                "temporal_status": "current",
            },
        }
    ]
    with pytest.raises(ValueError, match="JSON boolean"):
        MODULE.group_qrels(rows, "2.0")

    rows[0]["final"]["acceptable_citation"] = False  # type: ignore[index]
    rows[0]["final"]["abstention_correct"] = "no"  # type: ignore[index]
    with pytest.raises(ValueError, match="must not contain"):
        MODULE.group_qrels(rows, "2.0")


def test_runtime_receipt_records_latency_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POWER_EMBED_NUM_THREADS", "8")
    monkeypatch.setenv("POWER_RERANKER_BATCH_SIZE", "4")
    monkeypatch.setenv("POWER_BGE_RERANKER_MAX_TOKENS", "256")

    assert MODULE.runtime_configuration() == {
        "embed_num_threads": 8,
        "reranker_batch_size": 4,
        "reranker_max_tokens": 256,
    }


def test_current_fact_requires_one_jointly_current_acceptable_citation() -> None:
    qrels = MODULE.group_qrels(_rows(current_citation=False))
    queries = [
        {"query_id": "q-current", "journey": "current_fact"},
        {"query_id": "q-abstain", "journey": "abstention"},
    ]

    errors = MODULE.validate_metric_contract(queries, qrels)

    assert {error["code"] for error in errors} == {"current_citation_joint_gate_infeasible"}


def test_inconsistent_v1_query_labels_fail_closed() -> None:
    rows = _rows()
    rows[1]["final"]["abstention_correct"] = "yes"  # type: ignore[index]
    rows[1]["final"]["taxonomy"] = "historical_fact"  # type: ignore[index]
    qrels = MODULE.group_qrels(rows)

    errors = MODULE.validate_metric_contract(
        [
            {"query_id": "q-current", "journey": "current_fact"},
            {"query_id": "q-abstain", "journey": "abstention"},
        ],
        qrels,
    )

    assert {error["code"] for error in errors} >= {
        "ambiguous_query_abstention",
        "inconsistent_query_taxonomy",
    }


def test_misleading_relevance_is_supported_without_negative_dcg_gain() -> None:
    rows = _rows()
    rows[0]["final"]["relevance"] = -1  # type: ignore[index]
    rows[0]["final"]["acceptable_citation"] = False  # type: ignore[index]
    qrel = MODULE.group_qrels(rows)["q-current"]

    metrics = MODULE.result_metrics(
        {"query_id": "q-current", "journey": "current_fact"},
        ["doc-current", "doc-history"],
        qrel,
    )

    assert metrics["ndcg_at_10"] == pytest.approx(1.0 / MODULE.math.log2(3))
    assert metrics["mrr_at_10"] == 0.5

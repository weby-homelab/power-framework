"""Executable field-wise agreement and calibration contracts for M2."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = (
    Path(__file__).parents[1]
    / "benchmarks"
    / "human_retrieval"
    / "scripts"
    / "compute_agreement.py"
)
SPEC = importlib.util.spec_from_file_location("m2_human_agreement", SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _rows(*, ambiguous_abstention: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for participant in ("A", "B"):
        for query_id, relevance in (("q-1", (2, 0)), ("q-2", (1, -1))):
            for index, value in enumerate(relevance, 1):
                abstention = "no" if query_id == "q-1" else "yes"
                if ambiguous_abstention and participant == "B" and query_id == "q-2" and index == 2:
                    abstention = "uncertain"
                rows.append(
                    {
                        "participant_id": participant,
                        "query_id": query_id,
                        "document_id": f"doc-{index}",
                        "relevance": value,
                        "acceptable_citation": value >= 1,
                        "temporal_status": "current" if query_id == "q-1" else "not_applicable",
                        "taxonomy": "current_fact" if query_id == "q-1" else "abstention",
                        "query_abstention_correct": abstention,
                    }
                )
    return rows


def test_perfect_v2_packet_passes_calibration() -> None:
    receipt = MODULE.compute_receipt(_rows(), "2.0")

    assert receipt["status"] == "calibration_passed"
    assert receipt["pair_level"]["relevance"]["value"] == 1.0
    assert receipt["query_level"]["acceptable_citation_set"]["value"] == 1.0
    assert receipt["query_level"]["query_abstention"]["measurable_units"] == 2
    assert receipt["calibration_rule"]["passed"] is True


def test_ambiguous_query_abstention_fails_closed_on_coverage() -> None:
    receipt = MODULE.compute_receipt(_rows(ambiguous_abstention=True), "2.0")

    abstention = receipt["query_level"]["query_abstention"]
    assert abstention["measurable_units"] == 1
    assert abstention["total_units"] == 2
    assert receipt["calibration_rule"]["passed"] is False


def test_protocol_v1_is_diagnostic_only() -> None:
    rows = _rows()
    for row in rows:
        row["abstention_correct"] = row.pop("query_abstention_correct")

    receipt = MODULE.compute_receipt(rows, "1.0")

    assert receipt["calibration_rule"]["eligible"] is False
    assert receipt["status"] == "diagnostic_only"

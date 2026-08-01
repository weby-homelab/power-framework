"""Executable field-wise agreement and calibration contracts for M2."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

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
        for query_id, relevance in (("q-1", (2, 0)), ("q-2", (1, 0))):
            for index, value in enumerate(relevance, 1):
                rows.append(
                    {
                        "participant_id": participant,
                        "query_id": query_id,
                        "document_id": f"doc-{index}",
                        "relevance": value,
                        "acceptable_citation": value == 2,
                        "temporal_status": "current" if query_id == "q-1" else "not_applicable",
                    }
                )
    return rows


def test_perfect_v2_packet_passes_calibration() -> None:
    receipt = MODULE.compute_receipt(_rows(), "2.0")

    assert receipt["status"] == "calibration_passed"
    assert receipt["pair_level"]["relevance"]["value"] == 1.0
    assert receipt["query_level"]["acceptable_citation_set"]["value"] == 1.0
    assert receipt["calibration_rule"]["passed"] is True


def test_v2_has_no_manual_query_level_fields() -> None:
    receipt = MODULE.compute_receipt(_rows(), "2.0")

    assert "query_abstention" not in receipt["query_level"]
    assert "taxonomy" not in receipt["query_level"]
    assert receipt["calibration_rule"]["passed"] is True
    with pytest.raises(ValueError, match="relevance must be one of"):
        MODULE.quadratic_weighted_kappa([(0, -1)], categories=(0, 1, 2))


def test_v2_rejects_non_integer_relevance() -> None:
    rows = _rows()
    rows[0]["relevance"] = "2"

    with pytest.raises(ValueError, match="v2 relevance must be an integer"):
        MODULE.compute_receipt(rows, "2.0")


def test_v2_rejects_free_text_or_unknown_judgment_fields() -> None:
    rows = _rows()
    rows[0]["comment"] = "неоднозначно"

    with pytest.raises(ValueError, match="exact contract"):
        MODULE.compute_receipt(rows, "2.0")


def test_protocol_v1_is_diagnostic_only() -> None:
    rows = _rows()
    for row in rows:
        row["abstention_correct"] = "no" if row["query_id"] == "q-1" else "yes"
        row["taxonomy"] = "current_fact" if row["query_id"] == "q-1" else "abstention"

    receipt = MODULE.compute_receipt(rows, "1.0")

    assert receipt["calibration_rule"]["eligible"] is False
    assert receipt["status"] == "diagnostic_only"

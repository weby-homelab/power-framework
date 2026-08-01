#!/usr/bin/env python3
"""Create a de-identified field-wise human-agreement receipt.

The output binds the raw input by SHA-256 but contains no participant IDs or
individual labels. Frozen protocol v1 can be diagnosed; only protocol v2 is
eligible for the pre-registered calibration gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 20260801


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"judgment row {line_number} is not an object")
            rows.append(value)
    return rows


def percentile(values: list[float], percent: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percent / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def bootstrap_ci(
    units: list[Any], statistic: Callable[[list[Any]], float | None], seed: int
) -> list[float | None]:
    if not units:
        return [None, None]
    rng = random.Random(seed)  # noqa: S311 - deterministic evidence receipt
    estimates: list[float] = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sample = [units[rng.randrange(len(units))] for _ in units]
        estimate = statistic(sample)
        if estimate is not None:
            estimates.append(estimate)
    if not estimates:
        return [None, None]
    return [
        round(percentile(estimates, 2.5), 6),
        round(percentile(estimates, 97.5), 6),
    ]


def exact_receipt(matches: list[bool], *, total_units: int, seed: int) -> dict[str, Any]:
    value = statistics.fmean(float(match) for match in matches) if matches else None
    return {
        "value": round(value, 6) if value is not None else None,
        "ci95": bootstrap_ci(
            matches,
            lambda sample: statistics.fmean(float(match) for match in sample),
            seed,
        ),
        "matches": sum(matches),
        "measurable_units": len(matches),
        "total_units": total_units,
    }


def quadratic_weighted_kappa(pairs: list[tuple[int, int]]) -> float | None:
    if not pairs:
        return None
    categories = (-1, 0, 1, 2)
    index = {value: position for position, value in enumerate(categories)}
    matrix = [[0 for _ in categories] for _ in categories]
    for first, second in pairs:
        if first not in index or second not in index:
            raise ValueError("relevance must be one of -1, 0, 1, 2")
        matrix[index[first]][index[second]] += 1
    total = len(pairs)
    first_counts = [sum(row) for row in matrix]
    second_counts = [sum(matrix[row][column] for row in range(4)) for column in range(4)]
    weights = [[((row - column) / 3) ** 2 for column in range(4)] for row in range(4)]
    observed = (
        sum(weights[row][column] * matrix[row][column] for row in range(4) for column in range(4))
        / total
    )
    expected = (
        sum(
            weights[row][column] * first_counts[row] * second_counts[column] / total
            for row in range(4)
            for column in range(4)
        )
        / total
    )
    if expected == 0:
        return None
    return 1.0 - observed / expected


def compute_receipt(rows: list[dict[str, Any]], protocol_version: str) -> dict[str, Any]:
    participants = sorted({str(row.get("participant_id", "")) for row in rows})
    if len(participants) != 2 or not all(participants):
        raise ValueError("agreement requires exactly two non-empty participant IDs")
    pair_rows: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        query_id = str(row.get("query_id", ""))
        document_id = str(row.get("document_id", ""))
        participant_id = str(row.get("participant_id", ""))
        if not query_id or not document_id:
            raise ValueError("every judgment requires query_id and document_id")
        if participant_id in pair_rows[(query_id, document_id)]:
            raise ValueError("duplicate participant judgment for one query-document pair")
        pair_rows[(query_id, document_id)][participant_id] = row
    incomplete = [
        unit for unit, judgments in pair_rows.items() if set(judgments) != set(participants)
    ]
    if incomplete:
        raise ValueError("every query-document unit requires both participant judgments")

    units = sorted(pair_rows)
    first, second = participants
    relevance_pairs: list[tuple[int, int]] = []
    for unit in units:
        left_raw = pair_rows[unit][first]["relevance"]
        right_raw = pair_rows[unit][second]["relevance"]
        if protocol_version == "2.0" and any(
            not isinstance(value, int) or isinstance(value, bool) for value in (left_raw, right_raw)
        ):
            raise ValueError("v2 relevance must be an integer JSON value")
        left = int(left_raw)
        right = int(right_raw)
        minimum = 0 if protocol_version == "2.0" else -1
        if left < minimum or right < minimum or left > 2 or right > 2:
            raise ValueError(
                f"relevance must be between {minimum} and 2 for protocol {protocol_version}"
            )
        for participant in (first, second):
            judgment = pair_rows[unit][participant]
            citation = judgment.get("acceptable_citation")
            if protocol_version == "2.0" and not isinstance(citation, bool):
                raise ValueError("v2 acceptable_citation must be a JSON boolean")
            if bool(citation) and int(judgment["relevance"]) != 2:
                raise ValueError("v2 acceptable_citation requires relevance=2")
            if protocol_version == "2.0" and str(judgment.get("temporal_status")) not in {
                "current",
                "historical",
                "not_applicable",
            }:
                raise ValueError("v2 temporal_status is invalid")
            if protocol_version == "2.0" and (
                "taxonomy" in judgment or "abstention_correct" in judgment
            ):
                raise ValueError("v2 judgments must not contain taxonomy or abstention fields")
        relevance_pairs.append((left, right))
    relevance_exact = exact_receipt(
        [left == right for left, right in relevance_pairs],
        total_units=len(units),
        seed=BOOTSTRAP_SEED,
    )
    kappa = quadratic_weighted_kappa(relevance_pairs)
    relevance_exact["quadratic_weighted_kappa"] = {
        "value": round(kappa, 6) if kappa is not None else None,
        "ci95": bootstrap_ci(relevance_pairs, quadratic_weighted_kappa, BOOTSTRAP_SEED + 1),
        "n": len(relevance_pairs),
    }

    pair_fields: dict[str, dict[str, Any]] = {"relevance": relevance_exact}
    for offset, field in enumerate(("temporal_status",), 2):
        matches = [
            pair_rows[unit][first].get(field) == pair_rows[unit][second].get(field)
            for unit in units
        ]
        pair_fields[field] = exact_receipt(
            matches, total_units=len(units), seed=BOOTSTRAP_SEED + offset
        )

    query_ids = sorted({query_id for query_id, _ in units})
    citation_matches: list[bool] = []
    taxonomy_matches: list[bool] = []
    abstention_matches: list[bool] = []
    for query_id in query_ids:
        documents = [document_id for candidate, document_id in units if candidate == query_id]
        first_citations = {
            document_id
            for document_id in documents
            if bool(pair_rows[(query_id, document_id)][first].get("acceptable_citation"))
        }
        second_citations = {
            document_id
            for document_id in documents
            if bool(pair_rows[(query_id, document_id)][second].get("acceptable_citation"))
        }
        citation_matches.append(first_citations == second_citations)

        if protocol_version != "2.0":
            first_taxonomy = {
                str(pair_rows[(query_id, document_id)][first].get("taxonomy"))
                for document_id in documents
            }
            second_taxonomy = {
                str(pair_rows[(query_id, document_id)][second].get("taxonomy"))
                for document_id in documents
            }
            if len(first_taxonomy) == len(second_taxonomy) == 1:
                taxonomy_matches.append(first_taxonomy == second_taxonomy)

            first_abstention = {
                str(pair_rows[(query_id, document_id)][first].get("abstention_correct"))
                for document_id in documents
            }
            second_abstention = {
                str(pair_rows[(query_id, document_id)][second].get("abstention_correct"))
                for document_id in documents
            }
            if len(first_abstention) == len(second_abstention) == 1:
                abstention_matches.append(first_abstention == second_abstention)

    query_fields = {
        "acceptable_citation_set": exact_receipt(
            citation_matches, total_units=len(query_ids), seed=BOOTSTRAP_SEED + 10
        ),
    }
    if protocol_version != "2.0":
        query_fields["taxonomy"] = exact_receipt(
            taxonomy_matches, total_units=len(query_ids), seed=BOOTSTRAP_SEED + 11
        )
        query_fields["query_abstention"] = exact_receipt(
            abstention_matches, total_units=len(query_ids), seed=BOOTSTRAP_SEED + 12
        )
    kappa_receipt = pair_fields["relevance"]["quadratic_weighted_kappa"]
    calibration_passed = bool(
        protocol_version == "2.0"
        and relevance_exact["measurable_units"] == relevance_exact["total_units"]
        and relevance_exact["value"] is not None
        and relevance_exact["value"] >= 0.80
        and kappa_receipt["ci95"][0] is not None
        and kappa_receipt["ci95"][0] >= 0.60
    )
    status = "diagnostic_only"
    if protocol_version == "2.0":
        status = "calibration_passed" if calibration_passed else "calibration_failed"
    return {
        "schema_version": "power.m2.human-agreement.v2",
        "annotation_protocol_version": protocol_version,
        "status": status,
        "annotator_count": 2,
        "query_document_units": len(units),
        "query_units": len(query_ids),
        "bootstrap_samples": BOOTSTRAP_SAMPLES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "pair_level": pair_fields,
        "query_level": query_fields,
        "calibration_rule": {
            "relevance_exact_min": 0.80,
            "relevance_weighted_kappa_ci95_lower_min": 0.60,
            "passed": calibration_passed,
            "eligible": protocol_version == "2.0",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--protocol-version", required=True, choices=("1.0", "2.0"))
    args = parser.parse_args()
    receipt = compute_receipt(load_jsonl(args.input), args.protocol_version)
    receipt["raw_judgments_sha256"] = sha256_file(args.input)
    receipt["producer_sha256"] = sha256_file(Path(__file__).resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    sys.stdout.write(
        json.dumps(
            {
                "output": str(args.output),
                "status": receipt["status"],
                "raw_judgments_sha256": receipt["raw_judgments_sha256"],
            }
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

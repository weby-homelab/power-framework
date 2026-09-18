"""Pure R6A.1 admission helpers.

This module contains evaluation-only semantics.  It never participates in
production retrieval, never chooses a result, and never turns ground truth into
runtime input.
"""

from __future__ import annotations

from typing import Any

try:
    from scripts.benchmark_phase5e_shadow import normalize_source_id
    from scripts.phase5e_concept_mapping_r6 import source_id_to_concept
except ModuleNotFoundError:
    from benchmark_phase5e_shadow import normalize_source_id
    from phase5e_concept_mapping_r6 import source_id_to_concept


AUTHORITY_LEVEL: dict[str, int] = {
    "canonical": 0,
    "verified": 1,
    "curated": 2,
    "proposed": 3,
    "unverified": 4,
    "unknown": 5,
}
LOWER_AUTHORITY_OUTCOMES = frozenset({"do_not_cite", "report_conflict", "curated", "unverified"})


def normalized_concept_id(raw_source_id: str, alias_lookup: dict[str, str]) -> str:
    """Normalize runtime IDs and path-form IDs through one concept layer."""

    normalized = normalize_source_id(raw_source_id)
    return (
        source_id_to_concept(raw_source_id, alias_lookup)
        or source_id_to_concept(normalized, alias_lookup)
        or normalized
    )


def _has_canonical_provenance(item: dict[str, Any]) -> bool:
    authority = str(item.get("authority", "unknown")).lower()
    provenance = item.get("provenance")
    basis = (
        str(provenance.get("authority_basis", "UNKNOWN"))
        if isinstance(provenance, dict)
        else "UNKNOWN"
    )
    source_type = str(item.get("source_type", ""))
    return authority == "canonical" and (
        basis in {"CANONICAL_LEDGER", "CANONICAL_PROJECT_STATE"}
        or source_type in {"canonical_task", "canonical_decision", "canonical_project"}
    )


def evaluate_authority_metrics(
    *,
    expected_concept: str | None,
    owner_backed: bool,
    candidates: list[dict[str, Any]],
    ground_truth_row: dict[str, Any],
    alias_lookup: dict[str, str],
) -> dict[str, Any]:
    """Evaluate independent authority metrics over an already-produced result.

    Ground truth defines the eligible competitor set for measurement only.  It
    never supplies or reorders candidates.  Missing winners are never classified
    as outranked; path-form IDs and runtime IDs are normalized identically.
    """

    raw_ids = [str(item.get("source_id", "")) for item in candidates]
    concepts = [normalized_concept_id(raw_id, alias_lookup) for raw_id in raw_ids]
    winner_present = bool(owner_backed and expected_concept and expected_concept in concepts)
    winner_index = concepts.index(expected_concept) if winner_present and expected_concept else None
    winner_item = candidates[winner_index] if winner_index is not None else None
    winner_has_provenance = (
        _has_canonical_provenance(winner_item) if winner_item is not None else True
    )

    expected_winner_source = ground_truth_row.get("expected_authority_winner")
    lower_competitor_concepts: set[str] = set()
    for grade in ground_truth_row.get("graded_relevance", []):
        if not isinstance(grade, dict):
            continue
        source_id = str(grade.get("source_id", ""))
        if source_id == expected_winner_source:
            continue
        if grade.get("authority_outcome") in LOWER_AUTHORITY_OUTCOMES:
            lower_competitor_concepts.add(normalized_concept_id(source_id, alias_lookup))

    lower_indices = [
        index
        for index, (concept, item) in enumerate(zip(concepts, candidates, strict=True))
        if concept in lower_competitor_concepts
        and AUTHORITY_LEVEL.get(str(item.get("authority", "unknown")).lower(), 5) > 0
    ]
    outranked_applicable = bool(winner_present and lower_indices)
    canonical_winner_index = next(
        (
            index
            for index, (concept, item) in enumerate(zip(concepts, candidates, strict=True))
            if concept == expected_concept and _has_canonical_provenance(item)
        ),
        None,
    )
    authority_outranked = int(
        bool(
            outranked_applicable
            and canonical_winner_index is not None
            and min(lower_indices) < canonical_winner_index
        )
    )

    eligible_concepts = set(lower_competitor_concepts)
    if expected_concept:
        eligible_concepts.add(expected_concept)
    eligible_indices = [
        index for index, concept in enumerate(concepts) if concept in eligible_concepts
    ]
    authority_order_applicable = bool(
        winner_present and canonical_winner_index is not None and lower_indices
    )
    order_violations = 0
    if authority_order_applicable:
        seen_lower = False
        for index in eligible_indices:
            level = AUTHORITY_LEVEL.get(
                str(candidates[index].get("authority", "unknown")).lower(), 5
            )
            if level >= 4:
                seen_lower = True
            elif seen_lower and level <= 1:
                order_violations += 1

    return {
        "winner_present": winner_present,
        "winner_missing": int(owner_backed and not winner_present),
        "winner_has_canonical_provenance": winner_has_provenance,
        "provenance_failure": int(owner_backed and winner_present and not winner_has_provenance),
        "outranked_applicable": outranked_applicable,
        "authority_outranked": authority_outranked,
        "authority_order_applicable": authority_order_applicable,
        "authority_order_violations": order_violations,
        "normalized_concepts": concepts,
        "eligible_competitor_concepts": sorted(lower_competitor_concepts),
    }


__all__ = ["evaluate_authority_metrics", "normalized_concept_id"]

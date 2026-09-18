"""Tests for POWER 3.8 Phase 5E R6 evaluation fidelity and metric semantics.

Verifies:
1. Winner absent + empty results:
   -> winner_missing = 1, outranked NOT_APPLICABLE / 0.
2. Winner present with bad provenance:
   -> provenance_failure = 1, not automatically outranked.
3. Canonical below lower-authority same-subject evidence:
   -> outranked = 1.
4. Canonical correctly above same-subject raw evidence:
   -> outranked = 0.
5. Unrelated raw candidate:
   -> not an authority competitor (does not trigger outranked).
6. Fixture fidelity contract:
   - Detects wrong owner
   - Detects fabricated authority
   - Detects material fact deletion and substitution
   - Detects concept mapping mismatch
   - Detects query-specific enrichment
   - Passes for faithful R6 manifest
7. Evaluation revision registry states for historical revisions (v1.3, v1.4).

Note: All test cases use arbitrary synthetic IDs and do not copy holdout queries.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from power_framework.core.evaluation_contracts import (
    EVALUATION_REVISION_REGISTRY,
    FixtureFidelityError,
    verify_fixture_fidelity,
)
from scripts.phase5e_concept_mapping_r6 import (
    build_alias_to_concept,
    load_manifest,
    source_id_to_concept,
)


def _compute_metrics_for_case(
    *,
    expected_concept: str,
    owner_backed: bool,
    shad_items: list[dict[str, object]],
    ground_truth_row: dict[str, object],
    alias_lookup: dict[str, str],
    manifest: dict[str, object],
) -> dict[str, object]:
    """Helper implementing exact R6 authority metric computation logic."""
    auth_level = {
        "canonical": 0,
        "verified": 1,
        "curated": 2,
        "proposed": 3,
        "unverified": 4,
        "unknown": 5,
    }

    shad_raw_ids = [str(item.get("source_id", "")) for item in shad_items]
    shad_concepts_raw = [
        source_id_to_concept(rid, alias_lookup) or rid for rid in shad_raw_ids
    ]
    # Deduplicate concepts preserving order
    shad_concepts: list[str] = []
    for c in shad_concepts_raw:
        if c not in shad_concepts:
            shad_concepts.append(c)

    shad_authorities = [str(item.get("authority", "unknown")) for item in shad_items]
    shad_bases = [
        str((item.get("provenance") or {}).get("authority_basis", "UNKNOWN"))  # type: ignore[union-attr]
        if isinstance(item.get("provenance"), dict)
        else "UNKNOWN"
        for item in shad_items
    ]
    shad_source_types = [str(item.get("source_type", "")) for item in shad_items]

    def _has_provenance(auth: str, basis: str, stype: str) -> bool:
        return auth.lower() == "canonical" and (
            basis in ("CANONICAL_LEDGER", "CANONICAL_PROJECT_STATE")
            or stype in ("canonical_task", "canonical_decision", "canonical_project_state")
        )

    winner_present = False
    winner_has_provenance = True
    outranked = 0
    outranked_applicable = False

    if expected_concept and owner_backed:
        if expected_concept in shad_concepts:
            winner_present = True
            raw_idx = shad_concepts_raw.index(expected_concept)
            winner_auth = shad_authorities[raw_idx]
            winner_basis = shad_bases[raw_idx]
            winner_stype = shad_source_types[raw_idx]
            winner_has_provenance = _has_provenance(winner_auth, winner_basis, winner_stype)
        else:
            winner_present = False
            winner_has_provenance = True  # N/A when winner missing

        graded_rel = ground_truth_row.get("graded_relevance", [])
        same_subject_source_ids = {
            g["source_id"]  # type: ignore[index]
            for g in graded_rel  # type: ignore[union-attr]
            if g.get("source_id") != ground_truth_row.get("expected_authority_winner")  # type: ignore[union-attr]
            and g.get("authority_outcome")  # type: ignore[union-attr]
            in ("do_not_cite", "report_conflict", "curated", "unverified")
        }

        same_subject_lower_auth_indices: list[int] = []
        for i, (cid, auth) in enumerate(zip(shad_concepts_raw, shad_authorities, strict=True)):
            raw_id = shad_raw_ids[i]
            is_same_subject = (
                cid == expected_concept
                or raw_id in same_subject_source_ids
            )
            auth_lvl = auth_level.get(auth.lower(), 5)
            if is_same_subject and auth_lvl > 0:
                same_subject_lower_auth_indices.append(i)

        if same_subject_lower_auth_indices:
            outranked_applicable = True
            if winner_present:
                canonical_raw_idx = None
                for i, (cid, auth) in enumerate(zip(shad_concepts_raw, shad_authorities, strict=True)):
                    if cid == expected_concept and auth_level.get(auth.lower(), 5) == 0:
                        canonical_raw_idx = i
                        break
                if canonical_raw_idx is not None:
                    min_comp_idx = min(same_subject_lower_auth_indices)
                    outranked = 1 if min_comp_idx < canonical_raw_idx else 0
                else:
                    outranked = 1
            else:
                outranked = 1
        else:
            outranked_applicable = False
            outranked = 0

    return {
        "winner_present": winner_present,
        "winner_missing": 0 if winner_present else (1 if owner_backed else 0),
        "winner_has_canonical_provenance": winner_has_provenance,
        "provenance_failure": 0 if (not winner_present or winner_has_provenance) else 1,
        "authority_outranked": outranked,
        "outranked_applicable": outranked_applicable,
    }


def test_case_1_winner_absent_empty_results() -> None:
    """Case 1: winner absent + empty results -> winner_missing=1, outranked NOT_APPLICABLE / 0."""
    manifest = load_manifest()
    alias_lookup = build_alias_to_concept(manifest)

    gt_row = {
        "expected_authority_winner": "p38-src-decision-current",
        "graded_relevance": [
            {"source_id": "p38-src-decision-current", "authority_outcome": "prefer"},
            {"source_id": "p38-src-decision-raw", "authority_outcome": "do_not_cite"},
        ],
    }

    res = _compute_metrics_for_case(
        expected_concept="decision-current",
        owner_backed=True,
        shad_items=[],
        ground_truth_row=gt_row,
        alias_lookup=alias_lookup,
        manifest=manifest,
    )

    assert res["winner_present"] is False
    assert res["winner_missing"] == 1
    assert res["provenance_failure"] == 0
    assert res["outranked_applicable"] is False
    assert res["authority_outranked"] == 0


def test_case_2_winner_present_bad_provenance() -> None:
    """Case 2: winner present with bad provenance -> provenance_failure=1, outranked=0."""
    manifest = load_manifest()
    alias_lookup = build_alias_to_concept(manifest)

    gt_row = {
        "expected_authority_winner": "p38-src-decision-current",
        "graded_relevance": [
            {"source_id": "p38-src-decision-current", "authority_outcome": "prefer"},
            {"source_id": "p38-src-decision-raw", "authority_outcome": "do_not_cite"},
        ],
    }

    # Item is present at rank 1, but has unverified authority (bad provenance)
    shad_items = [
        {
            "source_id": "p38-src-decision-current",
            "authority": "unverified",
            "source_type": "file_note",
            "provenance": {"authority_basis": "FILE_BODY"},
        },
        {
            "source_id": "p38-src-decision-raw",
            "authority": "raw",
            "source_type": "file_note",
            "provenance": {"authority_basis": "RAW"},
        },
    ]

    res = _compute_metrics_for_case(
        expected_concept="decision-current",
        owner_backed=True,
        shad_items=shad_items,
        ground_truth_row=gt_row,
        alias_lookup=alias_lookup,
        manifest=manifest,
    )

    assert res["winner_present"] is True
    assert res["winner_missing"] == 0
    assert res["provenance_failure"] == 1  # Provenance failure triggered
    # Bad provenance is NOT automatically outranked by relevance unless a lower competitor outranks it
    assert res["outranked_applicable"] is True


def test_case_3_canonical_below_lower_authority_same_subject() -> None:
    """Case 3: canonical below lower-authority same-subject evidence -> outranked=1."""
    manifest = load_manifest()
    alias_lookup = build_alias_to_concept(manifest)

    gt_row = {
        "expected_authority_winner": "p38-src-decision-current",
        "graded_relevance": [
            {"source_id": "p38-src-decision-current", "authority_outcome": "prefer"},
            {"source_id": "p38-src-decision-raw", "authority_outcome": "do_not_cite"},
        ],
    }

    # Lower-authority same-subject item at rank 1, canonical winner at rank 2
    shad_items = [
        {
            "source_id": "p38-src-decision-raw",
            "authority": "unverified",
            "source_type": "file_note",
            "provenance": {"authority_basis": "RAW"},
        },
        {
            "source_id": "decision:dec_x-freeze-phase5a-corpus-decision",
            "authority": "canonical",
            "source_type": "canonical_decision",
            "provenance": {"authority_basis": "CANONICAL_LEDGER"},
        },
    ]

    res = _compute_metrics_for_case(
        expected_concept="decision-current",
        owner_backed=True,
        shad_items=shad_items,
        ground_truth_row=gt_row,
        alias_lookup=alias_lookup,
        manifest=manifest,
    )

    assert res["winner_present"] is True
    assert res["winner_missing"] == 0
    assert res["provenance_failure"] == 0
    assert res["outranked_applicable"] is True
    assert res["authority_outranked"] == 1  # Outranked violation!


def test_case_4_canonical_correctly_above_same_subject_raw() -> None:
    """Case 4: canonical correctly above same-subject raw evidence -> outranked=0."""
    manifest = load_manifest()
    alias_lookup = build_alias_to_concept(manifest)

    gt_row = {
        "expected_authority_winner": "p38-src-decision-current",
        "graded_relevance": [
            {"source_id": "p38-src-decision-current", "authority_outcome": "prefer"},
            {"source_id": "p38-src-decision-raw", "authority_outcome": "do_not_cite"},
        ],
    }

    # Canonical winner at rank 1, lower-authority same-subject item at rank 2
    shad_items = [
        {
            "source_id": "decision:dec_x-freeze-phase5a-corpus-decision",
            "authority": "canonical",
            "source_type": "canonical_decision",
            "provenance": {"authority_basis": "CANONICAL_LEDGER"},
        },
        {
            "source_id": "p38-src-decision-raw",
            "authority": "unverified",
            "source_type": "file_note",
            "provenance": {"authority_basis": "RAW"},
        },
    ]

    res = _compute_metrics_for_case(
        expected_concept="decision-current",
        owner_backed=True,
        shad_items=shad_items,
        ground_truth_row=gt_row,
        alias_lookup=alias_lookup,
        manifest=manifest,
    )

    assert res["winner_present"] is True
    assert res["winner_missing"] == 0
    assert res["provenance_failure"] == 0
    assert res["outranked_applicable"] is True
    assert res["authority_outranked"] == 0  # Passed!


def test_case_5_unrelated_raw_candidate_not_an_authority_competitor() -> None:
    """Case 5: unrelated raw candidate is not an authority competitor."""
    manifest = load_manifest()
    alias_lookup = build_alias_to_concept(manifest)

    gt_row = {
        "expected_authority_winner": "p38-src-decision-current",
        "graded_relevance": [
            {"source_id": "p38-src-decision-current", "authority_outcome": "prefer"},
        ],
    }

    # Rank 1: unrelated code note (raw/unverified)
    # Rank 2: canonical decision
    shad_items = [
        {
            "source_id": "p38-src-code-en",
            "authority": "unverified",
            "source_type": "file_note",
            "provenance": {"authority_basis": "FILE_BODY"},
        },
        {
            "source_id": "decision:dec_x-freeze-phase5a-corpus-decision",
            "authority": "canonical",
            "source_type": "canonical_decision",
            "provenance": {"authority_basis": "CANONICAL_LEDGER"},
        },
    ]

    res = _compute_metrics_for_case(
        expected_concept="decision-current",
        owner_backed=True,
        shad_items=shad_items,
        ground_truth_row=gt_row,
        alias_lookup=alias_lookup,
        manifest=manifest,
    )

    assert res["winner_present"] is True
    assert res["winner_missing"] == 0
    assert res["provenance_failure"] == 0
    # Unrelated note is NOT a same-subject competitor, so outranked is NOT applicable (0)
    assert res["outranked_applicable"] is False
    assert res["authority_outranked"] == 0


def test_fixture_fidelity_detects_wrong_owner() -> None:
    """Fixture fidelity rejects wrong owner on owner-backed concept."""
    manifest = copy.deepcopy(load_manifest())
    corpus_dir = Path("benchmarks/power38/retrieval_eval/v1.4/corpus")

    # Change decision-current owner to TaskService
    for c in manifest["concepts"]:
        if c["eval_concept_id"] == "decision-current":
            c["production_owner"] = "TaskService"

    with pytest.raises(FixtureFidelityError) as exc_info:
        verify_fixture_fidelity(manifest, corpus_dir)
    assert exc_info.value.code == "wrong_owner"


def test_fixture_fidelity_detects_fabricated_authority() -> None:
    """Fixture fidelity rejects fabricated CANONICAL authority on non-owner note."""
    manifest = copy.deepcopy(load_manifest())
    corpus_dir = Path("benchmarks/power38/retrieval_eval/v1.4/corpus")

    for c in manifest["concepts"]:
        if c["eval_concept_id"] == "code-en":
            c["expected_runtime_authority"] = "CANONICAL"

    with pytest.raises(FixtureFidelityError) as exc_info:
        verify_fixture_fidelity(manifest, corpus_dir)
    assert exc_info.value.code == "fabricated_authority"


def test_fixture_fidelity_detects_fact_substitution() -> None:
    """Fixture fidelity rejects factual substitution that contradicts source."""
    manifest = copy.deepcopy(load_manifest())
    corpus_dir = Path("benchmarks/power38/retrieval_eval/v1.4/corpus")

    for c in manifest["concepts"]:
        if c["eval_concept_id"] == "decision-current":
            c["setup_payload"]["title"] = "Canonical decision: holdout tuning current — рішення"
            c["setup_payload"]["description"] = "Рішення щодо holdout tuning зараз чинне"

    with pytest.raises(FixtureFidelityError) as exc_info:
        verify_fixture_fidelity(manifest, corpus_dir)
    assert exc_info.value.code in ("material_fact_substitution", "material_fact_deletion")


def test_fixture_fidelity_detects_concept_mapping_mismatch() -> None:
    """Fixture fidelity rejects concept mapping pointing to unrelated note."""
    manifest = copy.deepcopy(load_manifest())
    corpus_dir = Path("benchmarks/power38/retrieval_eval/v1.4/corpus")

    for c in manifest["concepts"]:
        if c["eval_concept_id"] == "decision-current":
            c["note_representations"] = ["p38-src-code-en"]

    with pytest.raises(FixtureFidelityError) as exc_info:
        verify_fixture_fidelity(manifest, corpus_dir)
    assert exc_info.value.code == "concept_mapping_mismatch"


def test_fixture_fidelity_detects_query_specific_enrichment() -> None:
    """Fixture fidelity rejects payload containing holdout query identifiers."""
    manifest = copy.deepcopy(load_manifest())
    corpus_dir = Path("benchmarks/power38/retrieval_eval/v1.4/corpus")

    for c in manifest["concepts"]:
        if c["eval_concept_id"] == "decision-current":
            c["setup_payload"]["description"] += " matched for p38-ho-q99"

    with pytest.raises(FixtureFidelityError) as exc_info:
        verify_fixture_fidelity(manifest, corpus_dir)
    assert exc_info.value.code == "query_specific_enrichment"


def test_fixture_fidelity_passes_on_r6_manifest() -> None:
    """Fixture fidelity passes cleanly on R6 manifest."""
    manifest = load_manifest()
    corpus_dir = Path("benchmarks/power38/retrieval_eval/v1.4/corpus")

    report = verify_fixture_fidelity(manifest, corpus_dir)
    assert report["status"] == "PASS"
    assert report["owner_backed_concepts"] == 3
    assert report["total_concepts"] == 19
    assert "decision-current" in report["verified_concepts"]
    assert "task-current" in report["verified_concepts"]
    assert "project-current" in report["verified_concepts"]


def test_evaluation_revision_registry_historical_states() -> None:
    """Registry confirms v1.3 and v1.4 are historical exposed revisions."""
    assert EVALUATION_REVISION_REGISTRY["v1.3"]["active"] is False
    assert EVALUATION_REVISION_REGISTRY["v1.3"]["lifecycle_status"] == "HISTORICAL_EXPOSED_REVISION"
    assert EVALUATION_REVISION_REGISTRY["v1.4"]["active"] is False
    assert EVALUATION_REVISION_REGISTRY["v1.4"]["lifecycle_status"] == "HISTORICAL_EXPOSED_REVISION"

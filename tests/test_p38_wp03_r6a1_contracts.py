"""R6A.1 admission-boundary regression tests.

These tests use only historical/exposed v1.4 development fixtures and small
synthetic review receipts.  They never execute a holdout or read the v1.5
candidate.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from power_framework.core import evaluation_contracts
from power_framework.core.evaluation_contracts import (
    SemanticReviewReceiptV2,
    compute_review_input_digest,
    load_verified_development_snapshot,
    validate_semantic_review_receipt_v2,
    verify_fixture_fidelity_v2,
)
from scripts.benchmark_phase5e_r6 import run_benchmark_r6
from scripts.phase5e_concept_mapping_r6 import load_manifest
from scripts.phase5e_r6a1_admission import evaluate_authority_metrics

REPO_ROOT = Path(__file__).parents[1]
V14_ROOT = REPO_ROOT / "benchmarks" / "power38" / "retrieval_eval" / "v1.4"
PHASE5E_ROOT = REPO_ROOT / "artifacts" / "project-state" / "phase-5e"


def _review_receipt(**overrides: object) -> SemanticReviewReceiptV2:
    values: dict[str, object] = {
        "algorithm_output_used": False,
        "ambiguous_count": 0,
        "candidate_revision": "v1.5",
        "defect_count": 0,
        "pass_count": 2,
        "retrieval_metrics_observed": False,
        "review_input_digest": "a" * 64,
        "query_set_digest": "b" * 64,
        "reviewer_id": "reviewer-a",
        "schema_version": "power.retrieval-semantic-review.v2",
        "scope_query_count": 2,
        "scope_source_count": 20,
        "source_corpus_digest": "c" * 64,
    }
    values.update(overrides)
    return SemanticReviewReceiptV2.model_validate(values)


def test_review_input_digest_is_deterministic_and_non_circular() -> None:
    kwargs = {
        "candidate_revision": "v1.5",
        "capability_contract_revision": "power.fast-capability.v1",
        "source_corpus_digest": "c" * 64,
        "source_metadata_identity": "d" * 64,
        "development_queries": [{"query_id": "dev-1", "query": "development"}],
        "holdout_queries": [{"query_id": "holdout-1", "query": "holdout"}],
        "development_ground_truth": [{"query_id": "dev-1", "source_id": "source-1"}],
        "holdout_ground_truth": [{"query_id": "holdout-1", "source_id": "source-2"}],
    }

    first = compute_review_input_digest(**kwargs)
    second = compute_review_input_digest(**dict(reversed(tuple(kwargs.items()))))

    assert first == second
    assert len(first) == 64
    assert first != compute_review_input_digest(**{**kwargs, "candidate_revision": "v1.6"})


def test_v2_review_receipt_binds_exact_candidate_inputs() -> None:
    receipt = _review_receipt()

    validate_semantic_review_receipt_v2(
        receipt,
        candidate_revision="v1.5",
        review_input_digest="a" * 64,
        query_set_digest="b" * 64,
        source_corpus_digest="c" * 64,
        scope_query_count=2,
        scope_source_count=20,
    )

    with pytest.raises(evaluation_contracts.EvaluationIntegrityError, match="revision"):
        validate_semantic_review_receipt_v2(
            receipt,
            candidate_revision="v1.6",
            review_input_digest="a" * 64,
            query_set_digest="b" * 64,
            source_corpus_digest="c" * 64,
            scope_query_count=2,
            scope_source_count=20,
        )

    with pytest.raises(evaluation_contracts.EvaluationIntegrityError, match="review input"):
        validate_semantic_review_receipt_v2(
            receipt,
            candidate_revision="v1.5",
            review_input_digest="d" * 64,
            query_set_digest="b" * 64,
            source_corpus_digest="c" * 64,
            scope_query_count=2,
            scope_source_count=20,
        )

    with pytest.raises(evaluation_contracts.EvaluationIntegrityError, match="query"):
        validate_semantic_review_receipt_v2(
            receipt,
            candidate_revision="v1.5",
            review_input_digest="a" * 64,
            query_set_digest="d" * 64,
            source_corpus_digest="c" * 64,
            scope_query_count=2,
            scope_source_count=20,
        )

    with pytest.raises(evaluation_contracts.EvaluationIntegrityError, match="source corpus"):
        validate_semantic_review_receipt_v2(
            receipt,
            candidate_revision="v1.5",
            review_input_digest="a" * 64,
            query_set_digest="b" * 64,
            source_corpus_digest="d" * 64,
            scope_query_count=2,
            scope_source_count=20,
        )


def test_historical_v1_receipt_remains_parseable() -> None:
    historical = {
        "algorithm_output_used": False,
        "ambiguous_count": 0,
        "defect_count": 0,
        "input_dataset_digest": "a" * 64,
        "input_query_set_digest": "b" * 64,
        "input_revision": "v1.1",
        "pass_count": 1,
        "retrieval_metrics_observed": False,
        "reviewer_id": "historical-reviewer",
        "schema_version": "power.retrieval-semantic-review.v1",
        "scope_query_count": 1,
        "scope_source_count": 20,
    }

    parsed = evaluation_contracts.SemanticReviewReceipt.model_validate(historical)

    assert parsed.schema_version == "power.retrieval-semantic-review.v1"
    assert parsed.input_revision == "v1.1"


def test_verified_development_snapshot_never_loads_holdout(monkeypatch: pytest.MonkeyPatch) -> None:
    original = evaluation_contracts._read_jsonl

    def no_holdout_read(path: Path) -> list[dict[str, object]]:
        assert "holdout" not in path.name
        return original(path)

    monkeypatch.setattr(evaluation_contracts, "_read_jsonl", no_holdout_read)
    snapshot = load_verified_development_snapshot(V14_ROOT, expected_revision="v1.4")

    assert snapshot.manifest.evaluation_revision == "v1.4"
    assert len(snapshot.queries) == 20
    assert len(snapshot.ground_truth) == 20
    assert snapshot.holdout_used is False


def test_verified_development_snapshot_rejects_wrong_revision() -> None:
    with pytest.raises(evaluation_contracts.EvaluationIntegrityError, match="revision"):
        load_verified_development_snapshot(V14_ROOT, expected_revision="v1.5")


def test_v2_receipt_rejects_explicit_nulls() -> None:
    with pytest.raises(ValidationError):
        _review_receipt(review_input_digest=None)


def _ownership_contract() -> dict[str, object]:
    return {
        "schema_version": "power.retrieval-evaluation-ownership.v1",
        "concepts": [
            {
                "concept_id": "decision-current",
                "source_representations": ["p38-src-decision-current"],
                "production_owner": "DecisionService",
                "required_authority": "CANONICAL",
                "runtime_object_class": "Decision",
                "required_lifecycle": "created_pending",
                "required_source_facts": ["freeze", "do not tune", "integrity verification"],
                "source_evidence_refs": ["p38-src-decision-current.md"],
                "runtime_object_id": "dec_x-freeze-phase5a-corpus-decision",
            },
            {
                "concept_id": "task-current",
                "source_representations": ["p38-src-task-current"],
                "production_owner": "TaskService",
                "required_authority": "CANONICAL",
                "runtime_object_class": "PowerTask",
                "required_lifecycle": "ready",
                "required_source_facts": ["verify", "ready", "read-only"],
                "source_evidence_refs": ["p38-src-task-current.md"],
                "runtime_object_id": "p38-task-current-corpus-verify",
            },
            {
                "concept_id": "project-current",
                "source_representations": ["p38-src-project-current"],
                "production_owner": "ProjectStateService",
                "required_authority": "CANONICAL",
                "runtime_object_class": "ProjectState",
                "required_lifecycle": "current_state_from_events",
                "required_source_facts": ["current", "Phase 5A", "Foundation Hardening"],
                "source_evidence_refs": ["p38-src-project-current.md"],
                "runtime_object_id": "prj_x-power-current-project-phase-status",
            },
        ],
    }


def test_fixture_fidelity_v2_uses_independent_ownership_contract() -> None:
    manifest = {
        "concepts": [
            {
                "eval_concept_id": "arbitrary-name",
                "owner_backed": True,
                "production_owner": "DecisionService",
                "expected_runtime_authority": "CANONICAL",
                "runtime_object_id": "dec_fixture",
                "runtime_object_class": "Decision",
                "setup_payload": {
                    "title": "Synthetic decision: freeze Phase 5A corpus",
                    "description": "Do not tune against holdout labels; integrity verification is separate.",
                    "decision_id": "dec_fixture",
                    "task_id": "p38-task-current-corpus-verify",
                },
                "note_representations": ["p38-src-decision-current"],
            }
        ]
    }

    ownership = _ownership_contract()
    ownership["concepts"] = [ownership["concepts"][0]]  # type: ignore[index]
    ownership["concepts"][0]["concept_id"] = "arbitrary-name"  # type: ignore[index]
    ownership["concepts"][0]["runtime_object_id"] = "dec_fixture"  # type: ignore[index]
    report = verify_fixture_fidelity_v2(
        manifest,
        ownership,
        V14_ROOT / "corpus",
    )

    assert report["status"] == "PASS"
    assert report["owner_backed_concepts"] == 1


def test_fixture_fidelity_v2_rejects_owner_inferred_from_name() -> None:
    manifest = {
        "concepts": [
            {
                "eval_concept_id": "decision-current",
                "owner_backed": True,
                "production_owner": "TaskService",
                "expected_runtime_authority": "CANONICAL",
                "runtime_object_id": "task_fixture",
                "runtime_object_class": "PowerTask",
                "setup_payload": {"title": "Verify corpus"},
                "note_representations": ["p38-src-decision-current"],
            }
        ]
    }

    with pytest.raises(evaluation_contracts.FixtureFidelityError, match="ownership"):
        verify_fixture_fidelity_v2(manifest, _ownership_contract(), V14_ROOT / "corpus")


def test_fixture_fidelity_v2_rejects_unsafe_note_reference(tmp_path: Path) -> None:
    manifest = {
        "concepts": [
            {
                "eval_concept_id": "decision-current",
                "owner_backed": True,
                "production_owner": "DecisionService",
                "expected_runtime_authority": "CANONICAL",
                "runtime_object_id": "dec_fixture",
                "runtime_object_class": "Decision",
                "setup_payload": {"title": "freeze", "description": "integrity verification"},
                "note_representations": ["p38-src-decision-current"],
            }
        ]
    }

    ownership = _ownership_contract()
    ownership["concepts"] = [ownership["concepts"][0]]  # type: ignore[index]
    ownership["concepts"][0]["runtime_object_id"] = "dec_fixture"  # type: ignore[index]
    ownership["concepts"][0]["source_evidence_refs"] = ["../outside.md"]  # type: ignore[index]
    with pytest.raises(evaluation_contracts.FixtureFidelityError) as exc_info:
        verify_fixture_fidelity_v2(manifest, ownership, tmp_path)
    assert exc_info.value.code == "ownership_contract_invalid"


def test_fixture_fidelity_v2_rejects_terminal_decision_without_resolution() -> None:
    manifest = {
        "concepts": [
            {
                "eval_concept_id": "arbitrary-name",
                "owner_backed": True,
                "production_owner": "DecisionService",
                "expected_runtime_authority": "CANONICAL",
                "runtime_object_id": "dec_fixture",
                "runtime_object_class": "Decision",
                "setup_payload": {
                    "title": "Approved freeze decision",
                    "description": "Final resolved decision",
                    "decision_id": "dec_fixture",
                    "task_id": "p38-task-current-corpus-verify",
                    "status": "approved",
                },
                "note_representations": ["p38-src-decision-current"],
            }
        ]
    }

    ownership = _ownership_contract()
    ownership["concepts"] = [ownership["concepts"][0]]  # type: ignore[index]
    ownership["concepts"][0]["concept_id"] = "arbitrary-name"  # type: ignore[index]
    ownership["concepts"][0]["runtime_object_id"] = "dec_fixture"  # type: ignore[index]
    with pytest.raises(evaluation_contracts.FixtureFidelityError) as exc_info:
        verify_fixture_fidelity_v2(manifest, ownership, V14_ROOT / "corpus")
    assert exc_info.value.code == "lifecycle_mismatch"


def test_r6a1_manifest_and_independent_ownership_contract_pass() -> None:
    manifest = load_manifest(PHASE5E_ROOT / "phase5e_runtime_fixture_manifest_r6a1.json")
    ownership = evaluation_contracts.load_bounded_json(
        PHASE5E_ROOT / "phase5e_evaluation_ownership_r6a1.json"
    )
    report = verify_fixture_fidelity_v2(
        manifest,
        ownership,
        V14_ROOT / "corpus",
    )

    assert report["status"] == "PASS"
    assert report["owner_backed_concepts"] == 3
    assert "runtime_main_sha" not in manifest
    assert manifest["manifest_version"] == "r6a1"
    assert manifest["runtime_base_sha"] == "10321b748a4b144c16720b4109c4c2c65fead83a"
    decision = next(
        concept
        for concept in manifest["concepts"]
        if concept["eval_concept_id"] == "decision-current"
    )
    assert "decision:dec_x-current-holdout-tuning-decision" not in decision["scoring_aliases"]


def test_r6a1_runner_rejects_holdout_before_corpus_access(tmp_path: Path) -> None:
    with pytest.raises(evaluation_contracts.EvaluationIntegrityError, match="holdout"):
        run_benchmark_r6(
            eval_corpus=tmp_path / "not-read",
            split="holdout",
            vault_dir=tmp_path / "vault",
            manifest_path=PHASE5E_ROOT / "phase5e_runtime_fixture_manifest_r6a1.json",
            expected_revision="v1.5",
        )


def test_fidelity_v2_rejects_unowned_concept_promoted_by_manifest() -> None:
    manifest = load_manifest(PHASE5E_ROOT / "phase5e_runtime_fixture_manifest_r6a1.json")
    for concept in manifest["concepts"]:
        if concept["eval_concept_id"] == "code-en":
            concept["owner_backed"] = True
            break
    ownership = evaluation_contracts.load_bounded_json(
        PHASE5E_ROOT / "phase5e_evaluation_ownership_r6a1.json"
    )

    with pytest.raises(evaluation_contracts.FixtureFidelityError, match="ownership"):
        verify_fixture_fidelity_v2(manifest, ownership, V14_ROOT / "corpus")


def test_fidelity_v2_rejects_symlinked_source_evidence(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "source.md"
    source.write_text("---\ntype: Project\ntimestamp: 2026-01-01\n---\nfreeze", encoding="utf-8")
    link = corpus / "linked.md"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlinks unavailable in this environment")
    manifest = {
        "concepts": [
            {
                "eval_concept_id": "arbitrary",
                "owner_backed": True,
                "production_owner": "DecisionService",
                "expected_runtime_authority": "CANONICAL",
                "runtime_object_class": "Decision",
                "runtime_object_id": "dec_fixture",
                "setup_payload": {
                    "title": "freeze",
                    "description": "freeze",
                    "decision_id": "dec_fixture",
                    "task_id": "p38-task-current-corpus-verify",
                },
                "note_representations": ["source"],
            }
        ]
    }
    ownership = {
        "schema_version": "power.retrieval-evaluation-ownership.v1",
        "concepts": [
            {
                "concept_id": "arbitrary",
                "source_representations": ["source"],
                "production_owner": "DecisionService",
                "runtime_object_class": "Decision",
                "runtime_object_id": "dec_fixture",
                "required_authority": "CANONICAL",
                "required_lifecycle": "created_pending",
                "required_source_facts": ["freeze"],
                "source_evidence_refs": ["linked.md"],
            }
        ],
    }

    with pytest.raises(evaluation_contracts.FixtureFidelityError, match="symlink"):
        verify_fixture_fidelity_v2(manifest, ownership, corpus)


def test_fidelity_v2_rejects_historical_query_id_markers() -> None:
    manifest = load_manifest(PHASE5E_ROOT / "phase5e_runtime_fixture_manifest_r6a1.json")
    decision = next(
        concept
        for concept in manifest["concepts"]
        if concept["eval_concept_id"] == "decision-current"
    )
    decision["setup_payload"]["description"] += " p38-v14-h07"
    ownership = evaluation_contracts.load_bounded_json(
        PHASE5E_ROOT / "phase5e_evaluation_ownership_r6a1.json"
    )

    with pytest.raises(evaluation_contracts.FixtureFidelityError, match="query identifier"):
        verify_fixture_fidelity_v2(manifest, ownership, V14_ROOT / "corpus")


def test_metric_provenance_accepts_canonical_duplicate_representation() -> None:
    manifest = {
        "concepts": [
            {
                "eval_concept_id": "decision-current",
                "scoring_aliases": ["p38-src-decision-current", "decision:dec_fixture"],
            }
        ]
    }
    from scripts.phase5e_concept_mapping_r6 import build_alias_to_concept

    result = evaluate_authority_metrics(
        expected_concept="decision-current",
        owner_backed=True,
        candidates=[
            {
                "source_id": "p38-src-decision-current",
                "authority": "unverified",
                "source_type": "file_note",
                "provenance": {"authority_basis": "RAW"},
            },
            {
                "source_id": "decision:dec_fixture",
                "authority": "canonical",
                "source_type": "canonical_decision",
                "provenance": {"authority_basis": "CANONICAL_LEDGER"},
            },
        ],
        ground_truth_row={
            "expected_authority_winner": "p38-src-decision-current",
            "graded_relevance": [
                {"source_id": "p38-src-decision-current", "authority_outcome": "prefer"}
            ],
        },
        alias_lookup=build_alias_to_concept(manifest),
    )

    assert result["winner_present"] is True
    assert result["provenance_failure"] == 0


def test_metric_semantics_missing_winner_is_not_outranked() -> None:
    manifest = {
        "concepts": [
            {
                "eval_concept_id": "decision-current",
                "scoring_aliases": [
                    "p38-src-decision-current",
                    "decision:dec_fixture",
                ],
            },
            {
                "eval_concept_id": "decision-raw",
                "scoring_aliases": [
                    "p38-src-decision-raw",
                ],
            },
        ]
    }
    from scripts.phase5e_concept_mapping_r6 import build_alias_to_concept

    result = evaluate_authority_metrics(
        expected_concept="decision-current",
        owner_backed=True,
        candidates=[],
        ground_truth_row={
            "expected_authority_winner": "p38-src-decision-current",
            "graded_relevance": [
                {"source_id": "p38-src-decision-current", "authority_outcome": "prefer"},
                {"source_id": "p38-src-decision-raw", "authority_outcome": "do_not_cite"},
            ],
        },
        alias_lookup=build_alias_to_concept(manifest),
    )

    assert result["winner_missing"] == 1
    assert result["provenance_failure"] == 0
    assert result["outranked_applicable"] is False
    assert result["authority_outranked"] == 0


def test_metric_semantics_normalizes_path_form_competitor_ids() -> None:
    manifest = {
        "concepts": [
            {
                "eval_concept_id": "decision-current",
                "scoring_aliases": [
                    "p38-src-decision-current",
                    "decision:dec_fixture",
                ],
            },
            {
                "eval_concept_id": "decision-raw",
                "scoring_aliases": [
                    "p38-src-decision-raw",
                ],
            },
        ]
    }
    from scripts.phase5e_concept_mapping_r6 import build_alias_to_concept

    result = evaluate_authority_metrics(
        expected_concept="decision-current",
        owner_backed=True,
        candidates=[
            {
                "source_id": "01_Projects/corpus/p38-src-decision-raw.md",
                "authority": "unverified",
                "source_type": "file_note",
                "provenance": {"authority_basis": "RAW"},
            },
            {
                "source_id": "decision:dec_fixture",
                "authority": "canonical",
                "source_type": "canonical_decision",
                "provenance": {"authority_basis": "CANONICAL_LEDGER"},
            },
        ],
        ground_truth_row={
            "expected_authority_winner": "p38-src-decision-current",
            "graded_relevance": [
                {"source_id": "p38-src-decision-current", "authority_outcome": "prefer"},
                {
                    "source_id": "p38-src-decision-raw",
                    "authority_outcome": "do_not_cite",
                },
            ],
        },
        alias_lookup=build_alias_to_concept(manifest),
    )

    assert result["winner_present"] is True
    assert result["outranked_applicable"] is True
    assert result["authority_outranked"] == 1
    assert result["eligible_competitor_concepts"] == ["decision-raw"]


def test_metric_semantics_authority_order_only_uses_eligible_competitors() -> None:
    manifest = {
        "concepts": [
            {
                "eval_concept_id": "decision-current",
                "scoring_aliases": [
                    "p38-src-decision-current",
                    "decision:dec_fixture",
                ],
            },
            {"eval_concept_id": "code-en", "scoring_aliases": ["p38-src-code-en"]},
        ]
    }
    from scripts.phase5e_concept_mapping_r6 import build_alias_to_concept

    result = evaluate_authority_metrics(
        expected_concept="decision-current",
        owner_backed=True,
        candidates=[
            {
                "source_id": "p38-src-code-en",
                "authority": "unverified",
                "source_type": "file_note",
            },
            {
                "source_id": "decision:dec_fixture",
                "authority": "canonical",
                "source_type": "canonical_decision",
                "provenance": {"authority_basis": "CANONICAL_LEDGER"},
            },
        ],
        ground_truth_row={
            "expected_authority_winner": "p38-src-decision-current",
            "graded_relevance": [
                {"source_id": "p38-src-decision-current", "authority_outcome": "prefer"},
            ],
        },
        alias_lookup=build_alias_to_concept(manifest),
    )

    assert result["authority_order_applicable"] is False
    assert result["authority_order_violations"] == 0

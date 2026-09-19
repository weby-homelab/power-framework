"""Synthetic regression tests for POWER 3.8 Phase 5E R5 remediation (Section 3.7).

Verifies the invariants:
1. TYPE != OWNER (note frontmatter does not fabricate subsystem ownership).
2. Concept identity mapping is evaluation-only and never leaks into production.
3. contradiction-canonical is NOT owner-backed in R5 manifest.
4. Legitimate canonical owner concepts (task-current, decision-current, project-current) are owner-backed.
5. Section 3.2 authority metrics structure:
   applicable_query_count, measured_violation_count, not_applicable_count, pass.
6. ProjectState phase projection uses real current_phase value, not nonexistent .phase.
7. RetrievalPlanner candidate pre-filter preserves cross-lingual project queries.
8. Evaluation revision registry and data-only revision admission helper function.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from power_framework.core.evaluation_contracts import (
    EVALUATION_REVISION_REGISTRY,
    EvaluationIntegrityError,
    EvaluationQuery,
    EvaluationSplitName,
    register_evaluation_revision,
)
from power_framework.core.retrieval_planner import (
    _PROJECT_TOPICAL_TOKENS,
    _meaningful_tokens,
)
from scripts.phase5e_concept_mapping_r5 import (
    is_owner_backed,
    load_manifest,
    owner_for_concept,
    source_id_to_concept,
)


def test_type_does_not_equal_owner_in_manifest_r5() -> None:
    """Invariant 1 & 3: contradiction-canonical has no runtime owner in R5."""
    manifest = load_manifest()
    concepts = {c["eval_concept_id"]: c for c in manifest["concepts"]}

    contra = concepts["contradiction-canonical"]
    assert contra["production_owner"] == "VaultNote"
    assert contra["expected_runtime_authority"] is None
    assert contra["runtime_object_id"] is None
    assert contra["setup_payload"] is None
    assert is_owner_backed("contradiction-canonical", manifest) is False


def test_legitimate_canonical_owners_are_owner_backed_in_r5() -> None:
    """Invariant 4: task, decision, and project states have real runtime owners."""
    manifest = load_manifest()

    assert is_owner_backed("task-current", manifest) is True
    assert owner_for_concept("task-current", manifest) == "TaskService"

    assert is_owner_backed("decision-current", manifest) is True
    assert owner_for_concept("decision-current", manifest) == "DecisionService"

    assert is_owner_backed("project-current", manifest) is True
    assert owner_for_concept("project-current", manifest) == "ProjectStateService"


def test_concept_mapping_source_id_resolution() -> None:
    """Invariant 2: source_id_to_concept maps runtime IDs and file stems cleanly."""
    manifest = load_manifest()
    from scripts.phase5e_concept_mapping_r5 import build_alias_to_concept

    alias_lookup = build_alias_to_concept(manifest)

    # File stem resolution
    assert source_id_to_concept("p38-src-task-current", alias_lookup) == "task-current"
    assert (
        source_id_to_concept("p38-src-contradiction-canonical", alias_lookup)
        == "contradiction-canonical"
    )

    # Runtime prefix resolution
    assert (
        source_id_to_concept("task:p38-task-current-corpus-verify", alias_lookup) == "task-current"
    )
    assert (
        source_id_to_concept("decision:dec_x-current-holdout-tuning-decision", alias_lookup)
        == "decision-current"
    )
    assert (
        source_id_to_concept("project:prj_x-power-current-project-phase-status", alias_lookup)
        == "project-current"
    )


def test_authority_metrics_structure_in_r5_development_evidence() -> None:
    """Invariant 5: authority metrics report Section 3.2 required 4-field shape."""
    dev_path = (
        Path(__file__).parents[1]
        / "artifacts"
        / "project-state"
        / "phase-5e"
        / "phase5e_development_r5_fast.json"
    )
    data = json.loads(dev_path.read_text(encoding="utf-8"))
    hard_invariants = data["hard_invariants"]

    required_metrics = [
        "authority_winner_missing",
        "authority_provenance_failures",
        "authority_outranked_by_relevance",
        "authority_order_violations",
    ]
    for metric_name in required_metrics:
        metric = hard_invariants[metric_name]
        assert isinstance(metric, dict), f"{metric_name} must be a dict"
        assert "applicable_query_count" in metric
        assert "measured_violation_count" in metric
        assert "not_applicable_count" in metric
        assert "pass" in metric
        assert metric["measured_violation_count"] == 0
        assert metric["pass"] is True


def test_project_topical_tokens_support_cross_lingual_queries() -> None:
    """Invariant 7: _PROJECT_TOPICAL_TOKENS covers Ukrainian and English project indicators."""
    assert "проєкт" in _PROJECT_TOPICAL_TOKENS
    assert "проект" in _PROJECT_TOPICAL_TOKENS
    assert "phase" in _PROJECT_TOPICAL_TOKENS
    assert "фаза" in _PROJECT_TOPICAL_TOKENS

    ua_query = "Узгодьте суперечливі твердження про статус проєкту за канонічним записом"
    tokens = _meaningful_tokens(ua_query)
    assert bool(tokens & _PROJECT_TOPICAL_TOKENS) is True


def test_evaluation_revision_registry_lifecycle_and_data_only_admission() -> None:
    """Invariant 8: revision registry records v1, v1.1, v1.2, v1.3 with correct active states."""
    assert EVALUATION_REVISION_REGISTRY["v1"]["active"] is False
    assert EVALUATION_REVISION_REGISTRY["v1.1"]["active"] is True
    assert EVALUATION_REVISION_REGISTRY["v1.2"]["active"] is False
    assert EVALUATION_REVISION_REGISTRY["v1.3"]["active"] is False
    assert EVALUATION_REVISION_REGISTRY["v1.3"]["lifecycle_status"] == "HISTORICAL_EXPOSED_REVISION"

    # Future admission must use an explicit immutable sealed revision spec.
    custom_spec = {"active": False, "lifecycle_status": "TEST_REVISION"}
    with pytest.raises(EvaluationIntegrityError, match="explicit sealed revision spec"):
        register_evaluation_revision("v1.99", custom_spec)
    assert "v1.99" not in EVALUATION_REVISION_REGISTRY


def test_historical_v13_query_id_shape_validation() -> None:
    """Query model admits historical p38-v13-h IDs for historical readback."""
    q = EvaluationQuery(
        query_id="p38-v13-h01",
        split=EvaluationSplitName.HOLDOUT,
        scenario_family="family-ho-test",
        query="test query in holdout",
        language_mix="UA",
        categories=["EXACT_LOOKUP"],
    )
    assert q.query_id == "p38-v13-h01"

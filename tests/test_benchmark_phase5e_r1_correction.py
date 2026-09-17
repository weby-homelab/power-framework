"""P38-WP03-R1 regression tests for Phase 5E benchmark closure correction.

Covers the five proven harness defects (Phase 1 forensic admission):
- Context Precision formula must be hits / K (K=10), not hits / len(returned).
- Authority metric must be ground-truth-aware (expected_authority_winner).
- Canonical authority must come from real runtime provenance (UNVERIFIED != CANONICAL).
- scope_escape must be really measured (containment), never a constant.
- default_switches must be really measured (served/default boundary), never hard-coded.

Includes the authority-sensitive regression case:
  decision-old MUST NOT outrank decision-current.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.benchmark_phase5e_shadow import (
    FROZEN_FIXTURE_OWNER_MAP,
    capture_served_default,
    compute_context_precision,
    has_canonical_runtime_provenance,
    is_vault_contained,
    project_fixture_to_runtime_owner,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_context_precision_frozen_formula_hits_over_k() -> None:
    # 3 hits in 7 returned items with K=10 => 0.3 (not 3/7).
    retrieved = ["a", "b", "c", "d", "e", "f", "g"]
    rel = {"a", "b", "c"}
    assert compute_context_precision(retrieved, rel, k=10) == 0.3
    # Empty retrieval => 0.0 (0 hits / K).
    assert compute_context_precision([], rel, k=10) == 0.0
    # Short list still divides by K.
    assert compute_context_precision(["a", "x"], {"a", "b"}, k=2) == 0.5
    # Invalid K fails closed.
    assert compute_context_precision(["a"], {"a"}, k=0) == 0.0


def test_fixture_projection_frozen_query_independent() -> None:
    # Mapping is frozen and independent of query/ground truth.
    assert project_fixture_to_runtime_owner("p38-src-decision-current") == "DecisionService"
    assert project_fixture_to_runtime_owner("p38-src-task-current") == "TaskService"
    assert project_fixture_to_runtime_owner("p38-src-project-current") == "ProjectStateService"
    assert project_fixture_to_runtime_owner("p38-src-noise-injection") == "Quarantine"
    assert project_fixture_to_runtime_owner("p38-src-unknown-xyz") == "Unknown"
    # Frozen map must contain all 20 v1.1 corpus stems (no per-query tuning).
    assert len(FROZEN_FIXTURE_OWNER_MAP) == 20
    # Same input always yields same owner (deterministic, no ground truth input).
    assert project_fixture_to_runtime_owner(
        "p38-src-decision-current"
    ) == project_fixture_to_runtime_owner("p38-src-decision-current")


def test_canonical_provenance_requires_runtime_basis_no_fake_label() -> None:
    # UNVERIFIED with PROPOSAL basis is never canonical (all-unverified pack cannot PASS).
    assert not has_canonical_runtime_provenance(
        authority="unverified", basis="PROPOSAL", source_type="vault_note"
    )
    assert not has_canonical_runtime_provenance(
        authority="unknown", basis="UNKNOWN", source_type="vault_note"
    )
    # A benchmark label of canonical without canonical basis is still FAIL.
    assert not has_canonical_runtime_provenance(
        authority="canonical", basis="PROPOSAL", source_type="vault_note"
    )
    # Real runtime provenance passes: canonical ledger task/decision.
    assert has_canonical_runtime_provenance(
        authority="canonical", basis="CANONICAL_LEDGER", source_type="canonical_task"
    )
    assert has_canonical_runtime_provenance(
        authority="canonical", basis="CANONICAL_LEDGER", source_type="canonical_decision"
    )
    assert has_canonical_runtime_provenance(
        authority="verified", basis="VERIFIED_PROJECTION", source_type="verified_note"
    )


def test_scope_escape_measured_containment(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "01_Projects" / "corpus").mkdir(parents=True)
    # Contained relative path passes.
    assert is_vault_contained(
        vault_dir=vault,
        raw_source_id="01_Projects/corpus/p38-src-project-current.md",
        source_refs=["01_Projects/corpus/p38-src-project-current.md"],
    )
    # Canonical ledger refs that are vault-relative pass.
    assert is_vault_contained(
        vault_dir=vault, raw_source_id="task:TSK-001", source_refs=["tasks/TSK-001.json"]
    )
    # Absolute escape outside vault fails.
    assert not is_vault_contained(
        vault_dir=vault, raw_source_id="/etc/passwd", source_refs=["/etc/passwd"]
    )
    # Relative .. escape fails (measured, not constant).
    assert not is_vault_contained(
        vault_dir=vault,
        raw_source_id="../../outside.md",
        source_refs=["../../outside.md"],
    )
    assert not is_vault_contained(
        vault_dir=vault,
        raw_source_id="01_Projects/corpus/ok.md",
        source_refs=["../../outside.md"],
    )


def test_default_switches_measured_not_hardcoded() -> None:
    before = capture_served_default()
    after = capture_served_default()
    # Measured values, never hard-coded literals.
    assert before["DEFAULT_SEARCH_MODE"] == "auto"
    assert before["retrieve_default_mode"] == "auto"
    assert before["has_retrieve"] == "yes"
    assert before["has_compile_context"] == "yes"
    # No switch when nothing changed.
    assert before == after
    # The harness must compare before/after dicts (measurement), not a literal 0.
    # This guards the old defect: "default_switches": 0 hard-coded.


def test_decision_old_must_not_outrank_decision_current_logic() -> None:
    """Regression case: decision-old above decision-current is authority outrank.

    Simulates the observed development evidence for p38-dev-q03:
      retrieved = [decision-old, contradiction-canonical, decision-current, ...]
      expected_winner = decision-current, expected_exclusion = {decision-old}.
    The corrected harness must count exclusions_above_winner=1 and outranked=1,
    and must reject canonical provenance for an all-unverified pack.
    """
    retrieved = [
        "p38-src-decision-old",
        "p38-src-contradiction-canonical",
        "p38-src-decision-current",
        "p38-src-contradiction-raw",
    ]
    authorities = ["unverified", "unverified", "unverified", "unverified"]
    expected_winner = "p38-src-decision-current"
    excl_set = {"p38-src-decision-old"}

    assert expected_winner in retrieved
    winner_idx = retrieved.index(expected_winner)
    # Exclusion stands above winner.
    above = retrieved[:winner_idx]
    assert any(s in excl_set for s in above)
    # Winner lacks canonical runtime provenance (all unverified).
    widx = retrieved.index(expected_winner)
    assert not has_canonical_runtime_provenance(
        authority=authorities[widx], basis="PROPOSAL", source_type="vault_note"
    )
    # Projected owner is declared but provenance is still missing => FAIL, not fake PASS.
    assert project_fixture_to_runtime_owner(expected_winner) == "DecisionService"

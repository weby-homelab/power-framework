"""Regression coverage for the single Phase 8 preregistered contract."""

from __future__ import annotations

from power_framework.phase8_contract import (
    CONTINUITY_INDEPENDENT_PROCESSES,
    HUMAN_EVIDENCE_THRESHOLD_PROFILE,
    PLAIN_HANDOFF_PROCESSES,
    REAL_VAULT_COMPARATORS,
    REAL_VAULT_EXPERIMENTS,
    REAL_VAULT_METRICS,
    SYNTHETIC_WORKFLOW_COUNT,
    phase8_contract,
)


def test_phase8_contract_snapshot_is_json_compatible_and_complete() -> None:
    contract = phase8_contract()

    assert contract["schema_version"] == "power.phase8-contract.v1"
    synthetic = contract["synthetic"]
    assert isinstance(synthetic, dict)
    assert synthetic["workflow_count"] == SYNTHETIC_WORKFLOW_COUNT
    assert synthetic["continuity_independent_processes"] == CONTINUITY_INDEPENDENT_PROCESSES
    assert synthetic["plain_handoff_processes"] == PLAIN_HANDOFF_PROCESSES

    real_vault = contract["real_vault"]
    assert isinstance(real_vault, dict)
    assert set(real_vault["experiments"]) == REAL_VAULT_EXPERIMENTS
    assert set(real_vault["metrics"]) == REAL_VAULT_METRICS
    assert set(real_vault["comparators"]) == REAL_VAULT_COMPARATORS

    human = contract["human_evidence"]
    assert isinstance(human, dict)
    assert human["threshold_profile"] == HUMAN_EVIDENCE_THRESHOLD_PROFILE

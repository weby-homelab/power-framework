"""Shared, versioned contract constants for POWER 3.5 Phase 8 evidence."""

from __future__ import annotations

from typing import Final

PHASE8_CONTRACT_SCHEMA_VERSION: Final = "power.phase8-contract.v1"
PHASE8_OUTCOME_SCHEMA_VERSION: Final = "power.phase8-outcome.v1"
PHASE8_CONTINUITY_SCHEMA_VERSION: Final = "power.phase8-continuity.v1"

SYNTHETIC_WORKFLOW_COUNT: Final = 20
CONTINUITY_INDEPENDENT_PROCESSES: Final = 60
PLAIN_HANDOFF_PROCESSES: Final = 40

REAL_VAULT_EXPERIMENTS: Final = frozenset({"build", "transfer", "import", "query"})
REAL_VAULT_METRICS: Final = frozenset(
    {
        "recall_at_10",
        "ndcg_at_10",
        "mrr_at_10",
        "evidence_use",
        "no_answer_score",
        "stale_answer_rate",
        "latency_p95_ms",
    }
)
REAL_VAULT_COMPARATORS: Final = frozenset({"fts", "auto", "semantic", "no_power"})
HUMAN_EVIDENCE_THRESHOLD_PROFILE: Final = "m2-v2.1"


def phase8_contract() -> dict[str, object]:
    """Return a JSON-compatible snapshot of the release contract."""
    return {
        "schema_version": PHASE8_CONTRACT_SCHEMA_VERSION,
        "synthetic": {
            "outcome_schema_version": PHASE8_OUTCOME_SCHEMA_VERSION,
            "continuity_schema_version": PHASE8_CONTINUITY_SCHEMA_VERSION,
            "workflow_count": SYNTHETIC_WORKFLOW_COUNT,
            "continuity_independent_processes": CONTINUITY_INDEPENDENT_PROCESSES,
            "plain_handoff_processes": PLAIN_HANDOFF_PROCESSES,
        },
        "real_vault": {
            "experiments": sorted(REAL_VAULT_EXPERIMENTS),
            "metrics": sorted(REAL_VAULT_METRICS),
            "comparators": sorted(REAL_VAULT_COMPARATORS),
        },
        "human_evidence": {"threshold_profile": HUMAN_EVIDENCE_THRESHOLD_PROFILE},
    }


__all__ = [
    "CONTINUITY_INDEPENDENT_PROCESSES",
    "HUMAN_EVIDENCE_THRESHOLD_PROFILE",
    "PHASE8_CONTINUITY_SCHEMA_VERSION",
    "PHASE8_CONTRACT_SCHEMA_VERSION",
    "PHASE8_OUTCOME_SCHEMA_VERSION",
    "PLAIN_HANDOFF_PROCESSES",
    "REAL_VAULT_COMPARATORS",
    "REAL_VAULT_EXPERIMENTS",
    "REAL_VAULT_METRICS",
    "SYNTHETIC_WORKFLOW_COUNT",
    "phase8_contract",
]

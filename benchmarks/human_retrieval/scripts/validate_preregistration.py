#!/usr/bin/env python3
"""Validate the M2-v2.1 retrieval policy before any new human packet exists."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

GATED_COMPARATORS = frozenset({"semantic", "hybrid", "reranked", "graph_assisted"})
DIAGNOSTIC_COMPARATORS = frozenset({"lexical", "vector"})
REQUIRED_THRESHOLDS = {
    "recall_at_10": 0.75,
    "ndcg_at_10": 0.7,
    "mrr_at_10": 0.7,
    "citation_provenance_accuracy": 0.95,
    "stale_answer_rate_max": 0.02,
    "abstention_quality": 0.9,
    "p95_latency_ms": 1500.0,
}


def validate_policy(policy: dict[str, Any]) -> list[str]:
    """Return actionable errors for one M2-v2.1 policy document."""
    errors: list[str] = []
    if policy.get("schema_version") != "power.m2.retrieval-preregistration.v1":
        errors.append("schema_version must be power.m2.retrieval-preregistration.v1")
    if policy.get("status") not in {
        "pending_curator_approval",
        "pre_registered_before_human_calibration",
    }:
        errors.append(
            "status must be pending_curator_approval or pre_registered_before_human_calibration"
        )
    if policy.get("protocol_version") != "2.0":
        errors.append("protocol_version must be 2.0")
    if policy.get("language") != "uk":
        errors.append("language must be uk")

    gated = policy.get("gated_comparators")
    diagnostic = policy.get("diagnostic_comparators")
    if (
        not isinstance(gated, list)
        or set(gated) != GATED_COMPARATORS
        or len(gated) != len(GATED_COMPARATORS)
    ):
        errors.append(
            "gated_comparators must contain semantic, hybrid, reranked and graph_assisted exactly once"
        )
    if (
        not isinstance(diagnostic, list)
        or set(diagnostic) != DIAGNOSTIC_COMPARATORS
        or len(diagnostic) != len(DIAGNOSTIC_COMPARATORS)
    ):
        errors.append("diagnostic_comparators must contain lexical and vector exactly once")
    if isinstance(gated, list) and isinstance(diagnostic, list) and set(gated) & set(diagnostic):
        errors.append("gated and diagnostic comparator sets must be disjoint")

    thresholds = policy.get("thresholds")
    if thresholds != REQUIRED_THRESHOLDS:
        errors.append("thresholds must match the canonical M2 policy")

    pool = policy.get("candidate_pool")
    if not isinstance(pool, dict):
        errors.append("candidate_pool is required")
    else:
        if (
            not isinstance(pool.get("top_k_per_comparator"), int)
            or pool["top_k_per_comparator"] < 10
        ):
            errors.append("candidate_pool.top_k_per_comparator must be an integer >= 10")
        if (
            not isinstance(pool.get("random_negative_count_per_query"), int)
            or pool["random_negative_count_per_query"] < 1
        ):
            errors.append("candidate_pool.random_negative_count_per_query must be an integer >= 1")
        if not isinstance(pool.get("random_seed"), int) or isinstance(pool["random_seed"], bool):
            errors.append("candidate_pool.random_seed must be a deterministic integer")
        errors.extend(
            f"candidate_pool.{key} must be true"
            for key in (
                "include_every_gated_comparator",
                "include_every_diagnostic_comparator",
                "deduplicate_by_document_id",
                "pool_is_frozen_before_human_judgment",
            )
            if pool.get(key) is not True
        )

    lexical = policy.get("lexical_policy")
    if not isinstance(lexical, dict):
        errors.append("lexical_policy is required")
    else:
        if lexical.get("operator") != "OR":
            errors.append("lexical_policy.operator must be OR")
        if lexical.get("status") != "diagnostic_only":
            errors.append("lexical_policy.status must be diagnostic_only")
        for key in ("report_metrics", "enforce_quality_thresholds"):
            expected = key == "report_metrics"
            if lexical.get(key) is not expected:
                errors.append(f"lexical_policy.{key} has an invalid value")
        errors.extend(
            f"lexical_policy.{key} must be false"
            for key in ("qrel_specific_synonyms", "fuzzy_matching", "post_hoc_tokenizer_changes")
            if lexical.get(key) is not False
        )

    human = policy.get("human_validation")
    if not isinstance(human, dict):
        errors.append("human_validation is required")
    else:
        errors.extend(
            f"human_validation.{key} must be true"
            for key in (
                "new_ukrainian_query_set",
                "independent_from_m2_v2_queries_and_qrels",
                "calibration_required_before_production",
                "raw_judgments_stay_restricted",
            )
            if human.get(key) is not True
        )
        if human.get("same_four_candidate_contract") is not True:
            errors.append("human_validation.same_four_candidate_contract must be true")
        for key, minimum in (
            ("minimum_relevance_exact", 0.8),
            ("minimum_weighted_kappa_ci95_lower", 0.6),
            ("minimum_temporal_exact", 0.8),
            ("minimum_citation_set_exact", 0.8),
        ):
            value = human.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < minimum:
                errors.append(f"human_validation.{key} must be >= {minimum}")

    sealed = policy.get("sealed_policy")
    if not isinstance(sealed, dict):
        errors.append("sealed_policy is required")
    else:
        if sealed.get("default_decision") != "do_not_open":
            errors.append("sealed_policy.default_decision must be do_not_open")
        errors.extend(
            f"sealed_policy.{key} must be true"
            for key in ("open_only_after_development_gate", "explicit_allow_sealed_required")
            if sealed.get(key) is not True
        )

    rules = policy.get("anti_leakage_rules")
    if (
        not isinstance(rules, list)
        or len(rules) < 4
        or not all(isinstance(rule, str) and rule for rule in rules)
    ):
        errors.append("anti_leakage_rules must contain at least four non-empty rules")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    args = parser.parse_args()
    try:
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"cannot read policy: {exc}")
    if not isinstance(policy, dict):
        parser.error("policy must be a JSON object")
    errors = validate_policy(policy)
    if errors:
        sys.stderr.write("".join(f"ERROR: {error}\n" for error in errors))
        return 1
    sys.stdout.write(f"M2-v2.1 preregistration valid: {args.policy}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

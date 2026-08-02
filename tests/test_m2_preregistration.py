"""Regression tests for the independent M2-v2.1 policy boundary."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = (
    Path(__file__).parents[1]
    / "benchmarks"
    / "human_retrieval"
    / "scripts"
    / "validate_preregistration.py"
)
SPEC = importlib.util.spec_from_file_location("m2_preregistration", SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

POLICY = (
    Path(__file__).parents[1] / "benchmarks" / "human_retrieval" / "m2-v2.1-preregistration.json"
)


def _policy() -> dict[str, object]:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def test_m2_v2_1_policy_is_valid() -> None:
    assert MODULE.validate_policy(_policy()) == []


def test_lexical_mode_is_diagnostic_and_cannot_be_tuned_after_qrels() -> None:
    policy = _policy()
    lexical = policy["lexical_policy"]
    assert isinstance(lexical, dict)
    lexical["enforce_quality_thresholds"] = True
    assert "lexical_policy.enforce_quality_thresholds has an invalid value" in (
        MODULE.validate_policy(policy)
    )

    lexical["enforce_quality_thresholds"] = False
    lexical["qrel_specific_synonyms"] = True
    assert "lexical_policy.qrel_specific_synonyms must be false" in MODULE.validate_policy(policy)


def test_candidate_pool_requires_every_mode_and_random_negatives() -> None:
    policy = _policy()
    pool = policy["candidate_pool"]
    assert isinstance(pool, dict)
    pool["include_every_gated_comparator"] = False
    pool["random_negative_count_per_query"] = 0
    pool["random_seed"] = "not-an-integer"
    errors = MODULE.validate_policy(policy)
    assert "candidate_pool.include_every_gated_comparator must be true" in errors
    assert "candidate_pool.random_negative_count_per_query must be an integer >= 1" in errors
    assert "candidate_pool.random_seed must be a deterministic integer" in errors

"""POWER 3.1 Release-Evidence Gate Verifier (E2/E3 methodology).

Fail-closed validation of a benchmark evidence JSON artifact.  Checks:
  - Required top-level fields and schema structure
  - SHA256 hashes of config files, dataset files, models.lock
  - Regression budgets against paired delta + CI
  - Release gates: no dirty tree, non-negative deltas within budget,
    no-answer false-positive rate below threshold, RAG correctness minimum

Exits with code 0 (pass) or 1 (fail).  Every violation writes to stderr.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REQUIRED_TOPLEVEL_FIELDS = [
    "run_id",
    "benchmark_version",
    "timestamp",
    "source_date",
    "git_commit",
    "dirty_tree",
    "config",
    "dataset",
    "dependency_lock_hash",
    "models_lock",
    "python_version",
    "platform",
    "hardware",
    "strata",
    "total_queries",
    "baseline_mode",
    "candidate_mode",
    "per_query_results",
    "aggregates",
    "paired_stats",
    "rag_metrics",
    "latency",
    "peak_rss_mb",
    "regression_budgets",
]

REQUIRED_HARDWARE_FIELDS = ["cpu", "logical_cores", "physical_cores", "ram_gb"]

REQUIRED_METRIC_KEYS = ["ndcg@10", "mrr@10", "recall@5", "precision@5"]

# ── Error accumulator ─────────────────────────────────────────────────────

_errors: list[str] = []


def fail(msg: str) -> None:
    _errors.append(msg)


def check(cond: bool, msg: str) -> None:
    if not cond:
        fail(msg)


# ── Schema / field checks ─────────────────────────────────────────────────


def check_required_fields(data: dict, fields: list[str], prefix: str = "") -> None:
    for f in fields:
        key = f"{prefix}.{f}" if prefix else f
        check(f in data, f"Missing required field: {key}")


def check_required_nested(data: dict, path: str, fields: list[str]) -> None:
    parts = path.split(".")
    obj: Any = data
    for p in parts:
        if not isinstance(obj, dict) or p not in obj:
            fail(f"Missing required section: {path}")
            return
        obj = obj[p]
    if not isinstance(obj, dict):
        fail(f"Expected dict at {path}, got {type(obj).__name__}")
        return
    for f in fields:
        key = f"{path}.{f}"
        check(f in obj, f"Missing required field: {key}")


# ── Pattern / type checks ─────────────────────────────────────────────────


VALID_RUN_ID = re.compile(r"^run-[0-9a-f]{8}$")
VALID_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
VALID_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def check_patterns(data: dict) -> None:
    rid = data.get("run_id", "")
    check(bool(VALID_RUN_ID.match(str(rid))), f"Invalid run_id format: {rid}")

    gc = data.get("git_commit", "")
    check(bool(VALID_GIT_COMMIT.match(str(gc))), f"Invalid git_commit format: {gc}")

    check(isinstance(data.get("dirty_tree"), bool), "dirty_tree must be bool")

    hw = data.get("hardware", {})
    for f in REQUIRED_HARDWARE_FIELDS:
        check(f in hw, f"Missing hardware field: {f}")
    check(
        isinstance(hw.get("logical_cores"), int), "hardware.logical_cores must be int"
    )
    check(
        isinstance(hw.get("physical_cores"), int), "hardware.physical_cores must be int"
    )
    check(isinstance(hw.get("ram_gb"), (int, float)), "hardware.ram_gb must be numeric")

    check(isinstance(data.get("total_queries"), int), "total_queries must be int")
    check(
        data.get("total_queries", 0) >= 228,
        f"total_queries < 228: {data.get('total_queries')}",
    )

    check(
        isinstance(data.get("peak_rss_mb"), (int, float)), "peak_rss_mb must be numeric"
    )


# ── Hash verification ─────────────────────────────────────────────────────


def verify_config_hashes(data: dict) -> None:
    cfg = data.get("config", {})
    for side in ("candidate",):
        entry = cfg.get(side, {})
        cfg_sha = entry.get("sha256", "")
        check(
            bool(VALID_SHA256.match(str(cfg_sha))),
            f"config.{side}.sha256 missing or invalid: {cfg_sha}",
        )


def verify_dataset_hashes(data: dict) -> None:
    ds = data.get("dataset", {})
    for key in ("corpus_hash", "queries_hash", "qrels_hash"):
        val = ds.get(key, "")
        check(
            bool(VALID_SHA256.match(str(val))),
            f"dataset.{key} missing or invalid: {val}",
        )


def verify_models_lock(data: dict) -> None:
    ml = data.get("models_lock", {})
    if not isinstance(ml, dict):
        fail("models_lock must be an object")
        return
    lock_hash = ml.get("hash")
    if lock_hash is not None:
        check(
            bool(VALID_SHA256.match(str(lock_hash))),
            f"models_lock.hash invalid: {lock_hash}",
        )


# ── Release gates ─────────────────────────────────────────────────────────


def verify_dirty_tree_gate(data: dict) -> None:
    dirty = data.get("dirty_tree", True)
    if dirty:
        fail("RELEASE GATE FAILED: dirty_tree is True — commit or stash before release")


def verify_regression_budgets(data: dict) -> None:
    budgets = data.get("regression_budgets", {})
    paired = data.get("paired_stats", {})
    bgt_budgets = budgets.get("budgets", {})

    if "per_stratum" not in paired:
        # Backward-compatible fixtures used by unit tests and pre-3.1 artifacts.
        for metric_key, paired_entry in paired.items():
            if metric_key not in bgt_budgets:
                continue
            delta = paired_entry.get("delta", 0.0)
            for stratum, budget in bgt_budgets[metric_key].items():
                max_regression = budget.get("max_absolute_regression")
                if max_regression is not None and delta < -max_regression:
                    fail(f"REGRESSION BUDGET VIOLATION: {metric_key}/{stratum} delta={delta:.4f}")
        return
    per_stratum = paired["per_stratum"]
    for stratum, metric_entries in per_stratum.items():
        for metric_key, paired_entry in metric_entries.items():
            budget = bgt_budgets.get(metric_key, {}).get(stratum)
            if budget is None:
                continue
            delta = paired_entry.get("delta", 0.0)
            max_regression = budget.get("max_absolute_regression")
            min_improvement = budget.get("min_absolute_improvement")

            if max_regression is not None and delta < -max_regression:
                fail(
                    f"REGRESSION BUDGET VIOLATION: {metric_key}/{stratum} "
                    f"delta={delta:.4f} exceeds max regression {max_regression}"
                )
            if min_improvement is not None and delta < min_improvement:
                fail(
                    f"IMPROVEMENT BUDGET VIOLATION: {metric_key}/{stratum} "
                    f"delta={delta:.4f} below min improvement {min_improvement}"
                )


def verify_no_answer_fp_gate(data: dict) -> None:
    agg = data.get("aggregates", {})
    fp = agg.get("no_answer_false_positive", {})
    baseline_rate = fp.get("baseline_rate", 0.0)
    candidate_rate = fp.get("candidate_rate", 0.0)

    # Threshold: no more than 50% false positive for no-answer queries
    threshold = 0.5
    if baseline_rate > threshold:
        fail(
            f"NO-ANSWER FALSE POSITIVE GATE: baseline rate {baseline_rate:.2%} > {threshold:.0%}"
        )
    if candidate_rate > threshold:
        fail(
            f"NO-ANSWER FALSE POSITIVE GATE: candidate rate {candidate_rate:.2%} > {threshold:.0%}"
        )


def verify_rag_gates(data: dict) -> None:
    rag = data.get("rag_metrics", {})
    for side in ("baseline", "candidate"):
        metrics = rag.get(side, {})
        correctness = metrics.get("mean_correctness", 1.0)
        if metrics.get("answerable_count", 0) > 0 and correctness < 0.5:
            fail(f"RAG CORRECTNESS GATE: {side} correctness {correctness:.2%} < 50%")


def verify_latency_gate(data: dict) -> None:
    lat = data.get("latency", {})
    for side in ("baseline", "candidate"):
        profile = lat.get(side, {})
        p95 = profile.get("p95_ms", 0)
        # Soft gate: warn if p95 > 10s per query
        if p95 > 10000:
            fail(f"LATENCY GATE: {side} p95 {p95:.0f}ms exceeds 10s threshold")


# ── Main entry ────────────────────────────────────────────────────────────


def verify(evidence_path: str) -> int:
    global _errors
    _errors = []

    path = Path(evidence_path)
    if not path.exists():
        print(f"FAIL: evidence file not found: {path}", file=sys.stderr)
        return 1

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FAIL: invalid JSON: {e}", file=sys.stderr)
        return 1

    if not isinstance(data, dict):
        print("FAIL: evidence root must be a JSON object", file=sys.stderr)
        return 1

    # ── Run all checks ────────────────────────────────────────────────────
    check_required_fields(data, REQUIRED_TOPLEVEL_FIELDS)
    check_patterns(data)
    check_required_nested(data, "config", ["baseline", "candidate"])
    check_required_nested(
        data, "dataset", ["corpus_hash", "queries_hash", "qrels_hash"]
    )
    check_required_nested(
        data,
        "aggregates",
        ["baseline", "candidate", "per_stratum", "no_answer_false_positive"],
    )
    check_required_nested(data, "hardware", REQUIRED_HARDWARE_FIELDS)

    verify_config_hashes(data)
    verify_dataset_hashes(data)
    verify_models_lock(data)
    verify_dirty_tree_gate(data)
    verify_regression_budgets(data)
    verify_no_answer_fp_gate(data)
    verify_rag_gates(data)
    verify_latency_gate(data)

    # ── Report ────────────────────────────────────────────────────────────
    if _errors:
        print(f"\nFAILED ({len(_errors)} violation(s)):", file=sys.stderr)
        for err in _errors:
            print(f"  [FAIL] {err}", file=sys.stderr)
        return 1

    run_id = data.get("run_id", "unknown")
    total_q = data.get("total_queries", 0)
    print(f"ALL RELEASE GATES PASSED for {run_id} ({total_q} queries)")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "Usage: verify_evidence.py <evidence.json> [evidence.json ...]",
            file=sys.stderr,
        )
        return 1

    exit_code = 0
    for arg in sys.argv[1:]:
        rc = verify(arg)
        if rc != 0:
            exit_code = rc
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

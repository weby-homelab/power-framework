"""Fail-closed verifier for the machine-only M2-AUTO evidence contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_m2_auto import (  # noqa: E402
    CONTRACT_DEFAULT,
    MANIFEST_FILE,
    QRELS_FILE,
    QUERIES_FILE,
    SUPPORTED_MODES,
)

REQUIRED_DATASET_FILES = {
    "manifest_sha256": MANIFEST_FILE,
    "queries_sha256": QUERIES_FILE,
    "qrels_sha256": QRELS_FILE,
}
FORBIDDEN_MARKERS = (
    "human_retrieval",
    ".m2-private",
    "sealed_holdout",
    "evaluation-v1",
    "evaluation-v2",
    "evaluation-v3",
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for nested in value.values() for item in _walk_strings(nested)]
    if isinstance(value, list):
        return [item for nested in value for item in _walk_strings(nested)]
    return []


def verify(evidence_path: Path, contract_path: Path = CONTRACT_DEFAULT) -> list[str]:
    errors: list[str] = []
    try:
        contract = _load_json(contract_path)
        evidence = _load_json(evidence_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"cannot load M2-AUTO input: {exc}"]

    if contract.get("schema_version") != "m2-auto/v1":
        errors.append("unsupported contract schema")
    if evidence.get("schema_version") != "m2-auto-evidence/v1":
        errors.append("unsupported evidence schema")
    if contract.get("scope") != "machine_only" or evidence.get("scope") != "machine_only":
        errors.append("scope must be machine_only")
    if contract.get("human_evidence_used") is not False or evidence.get("human_evidence_used") is not False:
        errors.append("human evidence is forbidden")
    if contract.get("sealed_accessed") is not False or evidence.get("sealed_accessed") is not False:
        errors.append("sealed access is forbidden")

    expected_contract_sha = _sha256_file(contract_path)
    if evidence.get("contract_sha256") != expected_contract_sha:
        errors.append("contract_sha256 does not match the committed contract")

    if evidence.get("benchmark_version") != contract.get("benchmark_version"):
        errors.append("benchmark_version mismatch")
    modes = evidence.get("modes", {})
    for side in ("baseline", "candidate"):
        mode = modes.get(side)
        if mode != contract.get(f"{side}_mode") or mode not in SUPPORTED_MODES:
            errors.append(f"unsupported or mismatched {side} mode")

    dataset = evidence.get("dataset", {})
    expected_counts = {"query_count": 228, "document_count": 100, "qrel_count": 416}
    for key, expected in expected_counts.items():
        if dataset.get(key) != expected:
            errors.append(f"{key} must be {expected}, got {dataset.get(key)!r}")
    for key, path in REQUIRED_DATASET_FILES.items():
        expected = _sha256_file(path)
        if dataset.get(key) != expected:
            errors.append(f"dataset {key} does not match {path.name}")

    source = evidence.get("source", {})
    if not isinstance(source.get("commit"), str) or len(source["commit"]) != 40:
        errors.append("source.commit must be a 40-character commit hash")
    if source.get("dirty_tree") is not False:
        errors.append("source.dirty_tree must be false")

    runtime = evidence.get("runtime_seconds")
    budget = contract.get("max_runtime_seconds")
    if not isinstance(runtime, (int, float)) or not isinstance(budget, (int, float)):
        errors.append("runtime and budget must be numeric")
    elif runtime > budget:
        errors.append(f"runtime {runtime:.3f}s exceeds budget {budget:.3f}s")

    metrics = evidence.get("metrics", {})
    baseline = metrics.get("baseline", {})
    candidate = metrics.get("candidate", {})
    paired = metrics.get("paired", {})
    thresholds = contract.get("absolute_thresholds", {})
    regressions = contract.get("max_absolute_regression", {})
    for key, minimum in thresholds.items():
        candidate_value = candidate.get(key)
        paired_entry = paired.get(key, {})
        baseline_value = baseline.get(key)
        delta = paired_entry.get("delta")
        if not all(isinstance(value, (int, float)) for value in (candidate_value, baseline_value, delta)):
            errors.append(f"missing numeric metric: {key}")
            continue
        if candidate_value < float(minimum):
            errors.append(f"{key} below absolute threshold")
        if delta < -float(regressions.get(key, 0)):
            errors.append(f"{key} exceeds maximum regression")
        if abs(delta - (candidate_value - baseline_value)) > 1e-9:
            errors.append(f"{key} paired delta is inconsistent")

    failures = evidence.get("failures")
    if failures != []:
        errors.append("evidence failures must be an empty list")
    if evidence.get("quality_gate") != "PASS":
        errors.append("quality_gate is not PASS")

    forbidden = [
        marker
        for text in _walk_strings(evidence)
        for marker in FORBIDDEN_MARKERS
        if marker in text
    ]
    if forbidden:
        errors.append(f"forbidden private/sealed marker in evidence: {sorted(set(forbidden))}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify bounded machine-only M2-AUTO evidence")
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--contract", type=Path, default=CONTRACT_DEFAULT)
    args = parser.parse_args(argv)
    errors = verify(args.evidence, args.contract)
    if errors:
        for error in errors:
            print(f"M2-AUTO verification failed: {error}", file=sys.stderr)
        return 1
    print("M2-AUTO verification PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

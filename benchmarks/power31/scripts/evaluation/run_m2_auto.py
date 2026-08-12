"""Run the bounded, machine-only M2-AUTO retrieval gate.

This gate deliberately uses only the committed synthetic POWER 3.1 dataset and
the real FTS/TF-vector search path. It never imports, reads, or opens the human
retrieval packets, private M2 receipts, or sealed holdout. The contract is a
regression/CI gate, not a human-quality or production-quality claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_release_evaluation import (  # noqa: E402
    DATASET_V1,
    MANIFEST_FILE,
    QRELS_FILE,
    QUERIES_FILE,
    _get_git_info,
    _search_and_collect,
    _sync_vault,
    compute_query_metrics,
    materialise_vault,
)

CONTRACT_DEFAULT = DATASET_V1.parent.parent / "configs" / "m2-auto-contract.v1.json"
SUPPORTED_MODES = frozenset({"fts", "vector", "hybrid"})


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _aggregate(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return {}
    return {key: sum(row[key] for row in rows) / len(rows) for key in rows[0]}


def _validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != "m2-auto/v1":
        raise ValueError("unsupported M2-AUTO contract")
    if contract.get("scope") != "machine_only":
        raise ValueError("M2-AUTO scope must be machine_only")
    if contract.get("human_evidence_used") is not False:
        raise ValueError("M2-AUTO forbids human evidence")
    if contract.get("sealed_accessed") is not False:
        raise ValueError("M2-AUTO forbids sealed access")
    for key in ("baseline_mode", "candidate_mode"):
        if contract.get(key) not in SUPPORTED_MODES:
            raise ValueError(f"unsupported bounded mode in {key}: {contract.get(key)!r}")
    if float(contract.get("max_runtime_seconds", 0)) <= 0:
        raise ValueError("max_runtime_seconds must be positive")
    top_k = int(contract.get("top_k", 0))
    if top_k < 1 or top_k > 100:
        raise ValueError("top_k must be between 1 and 100")


def run(contract_path: Path, vault_dir: Path | None, timestamp: str | None) -> dict[str, Any]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _validate_contract(contract)
    queries = _load_jsonl(QUERIES_FILE)
    qrels = _load_jsonl(QRELS_FILE)
    document_count = len(list((DATASET_V1 / "corpus").glob("*.md")))
    if len(queries) != 228 or document_count != 100 or len(qrels) != 416:
        raise ValueError(
            "unexpected power31.v1 dataset shape: "
            f"queries={len(queries)}, documents={document_count}, qrels={len(qrels)}"
        )
    qrels_map: dict[str, set[str]] = {}
    for row in qrels:
        qrels_map.setdefault(row["query_id"], set()).add(row["document_id"])

    target = vault_dir or Path(tempfile.mkdtemp(prefix="power-m2-auto-"))
    materialise_vault(target)
    started = time.monotonic()
    _sync_vault(target, sync_embeddings=False, force_rebuild=True)
    max_runtime = float(contract["max_runtime_seconds"])
    if time.monotonic() - started > max_runtime:
        raise TimeoutError("M2-AUTO runtime budget exceeded during index build")

    baseline_rows: list[dict[str, float]] = []
    candidate_rows: list[dict[str, float]] = []
    top_k = int(contract["top_k"])
    no_answer_counts = {"baseline": 0, "candidate": 0, "total": 0}
    for query in queries:
        if time.monotonic() - started > max_runtime:
            raise TimeoutError("M2-AUTO runtime budget exceeded during query evaluation")
        baseline = _search_and_collect(target, query["query"], contract["baseline_mode"], top_k)
        candidate = _search_and_collect(target, query["query"], contract["candidate_mode"], top_k)
        if query["query_class"] == "no_answer":
            no_answer_counts["total"] += 1
            no_answer_counts["baseline"] += bool(baseline)
            no_answer_counts["candidate"] += bool(candidate)
            continue
        relevant = qrels_map.get(query["query_id"], set())
        baseline_rows.append(compute_query_metrics(baseline, relevant))
        candidate_rows.append(compute_query_metrics(candidate, relevant))

    baseline_metrics = _aggregate(baseline_rows)
    candidate_metrics = _aggregate(candidate_rows)
    thresholds = contract["absolute_thresholds"]
    regressions = contract["max_absolute_regression"]
    failures: list[str] = []
    paired: dict[str, dict[str, Any]] = {}
    for key in thresholds:
        candidate_value = candidate_metrics.get(key, 0.0)
        baseline_value = baseline_metrics.get(key, 0.0)
        delta = candidate_value - baseline_value
        paired[key] = {"baseline": baseline_value, "candidate": candidate_value, "delta": delta}
        if candidate_value < float(thresholds[key]):
            failures.append(f"{key}: {candidate_value:.4f} < absolute {float(thresholds[key]):.4f}")
        if delta < -float(regressions[key]):
            failures.append(f"{key}: delta {delta:.4f} < -{float(regressions[key]):.4f}")

    commit, dirty = _get_git_info()
    timestamp_raw = timestamp or datetime.now(UTC).isoformat()
    return {
        "schema_version": "m2-auto-evidence/v1",
        "contract_sha256": _sha256_file(contract_path),
        "scope": "machine_only",
        "human_evidence_used": False,
        "sealed_accessed": False,
        "benchmark_version": contract["benchmark_version"],
        "source": {"commit": commit, "dirty_tree": dirty},
        "dataset": {
            "manifest_sha256": _sha256_file(MANIFEST_FILE),
            "queries_sha256": _sha256_file(QUERIES_FILE),
            "qrels_sha256": _sha256_file(QRELS_FILE),
            "query_count": len(queries),
            "document_count": document_count,
            "qrel_count": len(qrels),
        },
        "modes": {
            "baseline": contract["baseline_mode"],
            "candidate": contract["candidate_mode"],
        },
        "metrics": {
            "baseline": baseline_metrics,
            "candidate": candidate_metrics,
            "paired": paired,
        },
        "no_answer": {
            "baseline_returned": no_answer_counts["baseline"],
            "candidate_returned": no_answer_counts["candidate"],
            "total": no_answer_counts["total"],
            "diagnostic_only": True,
        },
        "runtime_seconds": round(time.monotonic() - started, 3),
        "runtime_budget_seconds": max_runtime,
        "thresholds": thresholds,
        "failures": failures,
        "quality_gate": "PASS" if not failures and not dirty else "FAIL",
        "timestamp": timestamp_raw,
        "limitations": [
            "Synthetic deterministic corpus and topic-assigned qrels only",
            "Machine-only CI regression gate; not human-quality evidence",
            "No production-quality or sealed-holdout claim",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run bounded machine-only M2-AUTO")
    parser.add_argument("--contract", type=Path, default=CONTRACT_DEFAULT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vault-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    args = parser.parse_args(argv)
    try:
        evidence = run(args.contract, args.vault_dir, args.timestamp)
    except (OSError, ValueError, TimeoutError) as exc:
        print(f"M2-AUTO execution failed: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"M2-AUTO {evidence['quality_gate']}: {evidence['runtime_seconds']}s")
    return 0 if evidence["quality_gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

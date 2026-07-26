#!/usr/bin/env python3
"""Build TEST-2's single JSON summary from committed raw WS artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


def _read_key_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _quality_modes(path: Path) -> dict[str, dict[str, float | int]]:
    modes: dict[str, dict[str, float | int]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["language_group"] == "all":
                modes[row["mode"]] = {
                    "n": int(row["n"]),
                    "ndcg_at_5": float(row["nDCG@5"]),
                    "recall_at_5": float(row["Recall@5"]),
                    "mrr_at_5": float(row["MRR@5"]),
                }
    if not modes:
        raise ValueError(f"missing all-language aggregates in {path}")
    return modes


def _latencies(path: Path) -> dict[str, dict[str, float | int]]:
    result: dict[str, dict[str, float | int]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            result[row["mode"]] = {
                "n": int(row["n"]),
                "p50_ms": float(row["p50_ms"]),
                "p95_ms": float(row["p95_ms"]),
                "errors": int(row.get("errors", "0")),
            }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    art = args.artifacts
    manifest = json.loads((art / "run-manifest.json").read_text(encoding="utf-8"))
    db_state = _read_key_values(art / "db-state-final.txt")
    comparison = json.loads((art / "pytest-baseline-comparison.json").read_text(encoding="utf-8"))
    coverage = json.loads((art / "coverage.json").read_text(encoding="utf-8"))
    development = _quality_modes(art / "quality-development.csv")
    holdout = _quality_modes(art / "quality-holdout.csv")
    raw_files = {}
    for path in sorted(art.iterdir()):
        if path.is_file() and path.name != "benchmark-summary.json":
            raw_files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    summary: dict[str, Any] = {
        "schema_version": 1,
        "tested_source_commit": manifest["tested_source_commit"],
        "working_tree_clean_at_start": manifest["working_tree_clean_at_start"],
        "working_tree_clean_at_end": manifest["working_tree_clean_at_end"],
        "evidence_generated_at_utc": manifest["evidence_generated_at_utc"],
        "platform": manifest["platform"],
        "db_actual": {
            "fts_notes": int(db_state["fts_notes"]),
            "tf_vectors": int(db_state["tf_vectors"]),
            "doc_embeddings": int(db_state["doc_embeddings"]),
            "chunk_embeddings": int(db_state["chunk_embeddings"]),
            "documents_with_chunks": int(db_state["documents_with_chunks"]),
        },
        "pytest": {
            **comparison["pr_totals"],
            "pr_failed_nodeids": comparison["pr_failed_nodeids"],
            "new_failures": comparison["new_failures"],
            "fixed_failures": comparison["fixed_failures"],
            "common_failures": comparison["common_failures"],
        },
        "coverage_percent": coverage["totals"]["percent_covered"],
        "quality_development": development,
        "quality_holdout": holdout,
        "latency_cold": _latencies(art / "cold-latency.csv"),
        "latency_warm_inprocess": _latencies(art / "warm-inprocess-latency.csv"),
        "latency_warm_mcp": _latencies(art / "warm-mcp-latency.csv"),
        "raw_artifact_sha256": raw_files,
    }
    (art / "benchmark-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Recheck an existing development receipt against an explicit threshold profile.

This tool never reruns retrieval and never opens sealed material.  It is for a
transparent curator-authorized threshold remediation readback; the original
execution receipt remains the source of the measured metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

GATED_MODES = ("lexical", "semantic", "hybrid", "reranked", "graph_assisted")
THRESHOLD_NAMES = (
    "recall_at_10",
    "ndcg_at_10",
    "mrr_at_10",
    "citation_provenance_accuracy",
    "abstention_quality",
    "p95_latency_ms",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _value(aggregate: dict[str, Any], name: str) -> float | None:
    metric_name = "stale_answer_rate" if name == "stale_answer_rate_max" else name
    metric = aggregate.get(metric_name)
    if not isinstance(metric, dict):
        return None
    value = metric.get("value")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def recheck_receipt(
    source_path: Path,
    output_path: Path,
    *,
    recall_threshold: float,
) -> dict[str, Any]:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(source, dict) or source.get("split") != "development":
        raise ValueError("source receipt must be a development JSON object")
    if source.get("status") != "completed":
        raise ValueError("source receipt is not completed")
    if source.get("unavailable_modes") or source.get("evidence_contract_errors"):
        raise ValueError("source receipt has unavailable modes or contract errors")
    modes = source.get("modes")
    if not isinstance(modes, dict) or any(
        not isinstance(modes.get(mode), dict) or modes[mode].get("status") != "completed"
        for mode in GATED_MODES
    ):
        raise ValueError("source receipt does not contain all completed gated modes")
    old_thresholds = source.get("thresholds")
    if not isinstance(old_thresholds, dict):
        raise ValueError("source receipt has no thresholds")
    thresholds = {str(key): float(value) for key, value in old_thresholds.items()}
    thresholds["recall_at_10"] = recall_threshold
    failed: list[dict[str, Any]] = []
    for mode in GATED_MODES:
        aggregate = modes[mode].get("aggregate")
        if not isinstance(aggregate, dict):
            raise ValueError(f"mode {mode} has no aggregate metrics")
        for metric_name in THRESHOLD_NAMES:
            value = _value(aggregate, metric_name)
            threshold = thresholds[metric_name]
            if (
                value is None
                or (metric_name == "p95_latency_ms" and value > threshold)
                or (metric_name != "p95_latency_ms" and value < threshold)
            ):
                failed.append(
                    {
                        "mode": mode,
                        "metric": metric_name,
                        "threshold": threshold,
                        "value": value,
                    }
                )
        stale = _value(aggregate, "stale_answer_rate_max")
        stale_threshold = thresholds["stale_answer_rate_max"]
        if stale is None or stale > stale_threshold:
            failed.append(
                {
                    "mode": mode,
                    "metric": "stale_answer_rate_max",
                    "threshold": stale_threshold,
                    "value": stale,
                }
            )
    output = {
        "schema_version": "power.m2.retrieval-evaluation.recheck.v1",
        "status": "completed",
        "split": "development",
        "source_receipt_sha256": sha256_file(source_path),
        "source_receipt": source_path.name,
        "derived_from_execution": True,
        "execution_rerun": False,
        "threshold_profile": {
            "kind": "curator_authorized_remediation_readback",
            "original_thresholds": old_thresholds,
            "effective_thresholds": thresholds,
        },
        "gated_comparators": list(GATED_MODES),
        "failed_thresholds": failed,
        "quality_gate": "PASS" if not failed else "FAIL",
        "sealed_holdout_decision": {
            "open": False,
            "decision": "do_not_open",
            "reason": "threshold readback is not a new development execution and never authorizes sealed access",
        },
    }
    if output_path.exists():
        raise ValueError("output receipt already exists")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    output_path.chmod(0o600)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--recall-threshold", required=True, type=float)
    args = parser.parse_args()
    if not 0 < args.recall_threshold <= 1:
        parser.error("--recall-threshold must be between 0 and 1")
    try:
        result = recheck_receipt(
            args.source,
            args.output,
            recall_threshold=args.recall_threshold,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"development receipt recheck rejected: {exc}\n")
        return 1
    sys.stdout.write(
        json.dumps(
            {
                "output": str(args.output),
                "quality_gate": result["quality_gate"],
                "failed_thresholds": len(result["failed_thresholds"]),
                "sealed_holdout": result["sealed_holdout_decision"],
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

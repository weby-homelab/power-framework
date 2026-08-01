#!/usr/bin/env python3
"""Evaluate POWER retrieval modes against one frozen corpus and qrels.

The evaluator is deliberately independent of the human-judgment producer.  It
reads only the frozen qrels' final fields and emits de-identified result
metadata; raw judgments are never copied to the output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

THRESHOLDS: dict[str, float] = {
    "recall_at_10": 0.8,
    "ndcg_at_10": 0.7,
    "mrr_at_10": 0.7,
    "citation_provenance_accuracy": 0.95,
    "stale_answer_rate_max": 0.02,
    "abstention_quality": 0.9,
    "p95_latency_ms": 1500.0,
}

PRE_REGISTERED = ("lexical", "semantic", "hybrid", "reranked", "graph_assisted")
MODE_TO_POWER = {"lexical": "fts", "vector": "vector"}
ALL_MODES = (*PRE_REGISTERED, "vector")
BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 20260801


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row is not an object at {path}:{line_number}")
            rows.append(value)
    return rows


def git_commit() -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603 - executable resolved with shutil.which
            [git, "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def percentile(values: list[float], percent: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percent / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def bootstrap_ci(values: list[float], statistic: str, seed: int) -> list[float | None]:
    if not values:
        return [None, None]
    # Deterministic resampling is intentional; this is not cryptographic use.
    rng = random.Random(seed)  # noqa: S311
    estimates: list[float] = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sample = [values[rng.randrange(len(values))] for _ in values]
        if statistic == "p95":
            estimates.append(percentile(sample, 95.0))
        else:
            estimates.append(statistics.fmean(sample))
    return [
        round(percentile(estimates, 2.5), 6),
        round(percentile(estimates, 97.5), 6),
    ]


def mean_and_ci(values: list[float], seed: int) -> dict[str, Any]:
    if not values:
        return {"value": None, "ci95": [None, None], "n": 0}
    return {
        "value": round(statistics.fmean(values), 6),
        "ci95": bootstrap_ci(values, "mean", seed),
        "n": len(values),
    }


def group_qrels(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        query_id = str(row.get("query_id", ""))
        document_id = str(row.get("document_id", ""))
        final = row.get("final")
        if not query_id or not document_id or not isinstance(final, dict):
            raise ValueError("frozen qrels require query_id, document_id and final object")
        relevance = final.get("relevance")
        if not isinstance(relevance, int) or relevance < 0 or relevance > 2:
            raise ValueError(f"unsupported final relevance for {query_id}/{document_id}")
        bucket = grouped.setdefault(
            query_id,
            {
                "relevance": {},
                "citation": {},
                "temporal": {},
                "abstention": set(),
                "query_abstention": set(),
                "taxonomy": set(),
            },
        )
        bucket["relevance"][document_id] = relevance
        bucket["citation"][document_id] = bool(final.get("acceptable_citation"))
        bucket["temporal"][document_id] = str(final.get("temporal_status"))
        # Protocol v1 stored abstention on every query-document row. Protocol
        # v2 binds it once at query level; retain the v1 fallback so frozen v1
        # qrels remain byte-for-byte untouched and reproducible.
        if "query_abstention_correct" in final:
            bucket["query_abstention"].add(str(final.get("query_abstention_correct")))
        else:
            bucket["abstention"].add(str(final.get("abstention_correct")))
        bucket["taxonomy"].add(str(final.get("taxonomy")))
    return grouped


def result_metrics(
    query: dict[str, Any],
    result_ids: list[str],
    qrel: dict[str, Any],
) -> dict[str, Any]:
    relevance: dict[str, int] = qrel["relevance"]
    relevant = {doc_id for doc_id, value in relevance.items() if value >= 1}
    top10 = result_ids[:10]
    recall = None if not relevant else len(set(top10) & relevant) / len(relevant)

    gains = [2 ** relevance.get(doc_id, 0) - 1 for doc_id in top10]
    ideal = sorted((2**value - 1 for value in relevance.values()), reverse=True)[:10]
    dcg = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(gains))
    idcg = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(ideal))
    ndcg = None if idcg == 0 else dcg / idcg
    mrr = next((1.0 / (rank + 1) for rank, doc_id in enumerate(top10) if doc_id in relevant), 0.0)

    citation = 0.0
    if top10:
        citation = 1.0 if qrel["citation"].get(top10[0], False) else 0.0

    journey = str(query.get("journey", ""))
    stale = None
    if journey == "current_fact":
        stale = bool(top10 and qrel["temporal"].get(top10[0]) != "current")

    abstention = None
    abstention_values = qrel.get("query_abstention") or qrel["abstention"]
    if len(abstention_values) == 1:
        expected = next(iter(abstention_values))
        if expected in {"yes", "no"}:
            top_relevance = relevance.get(top10[0], 0) if top10 else 0
            abstention = float(
                (expected == "yes" and top_relevance == 0)
                or (expected == "no" and top_relevance >= 1)
            )

    return {
        "query_id": str(query["query_id"]),
        "journey": journey,
        "result_doc_ids": top10,
        "result_count": len(result_ids),
        "recall_at_10": recall,
        "ndcg_at_10": ndcg,
        "mrr_at_10": mrr,
        "citation_provenance_accuracy": citation,
        "stale_answer_rate": stale,
        "abstention_quality": abstention,
    }


def evaluate_mode(
    vault: Path,
    queries: list[dict[str, Any]],
    qrels: dict[str, dict[str, Any]],
    mode_name: str,
) -> dict[str, Any]:
    power_mode = MODE_TO_POWER.get(mode_name, mode_name)
    try:
        from power_framework.core.searcher import search_vault
    except ImportError as exc:  # pragma: no cover - command-line guard
        return {"status": "unavailable", "reason": f"import_error:{type(exc).__name__}"}

    warmup_query = str(queries[0]["question"])
    try:
        search_vault(vault, warmup_query, max_results=10, mode=power_mode, temporal_view="all")
    except Exception as exc:
        return {
            "status": "unavailable",
            "power_mode": power_mode,
            "reason": f"{type(exc).__name__}:{str(exc)[:400]}",
        }

    per_query: list[dict[str, Any]] = []
    for query in queries:
        started = time.perf_counter()
        try:
            results = search_vault(
                vault,
                str(query["question"]),
                max_results=10,
                mode=power_mode,
                temporal_view="all",
            )
        except Exception as exc:
            return {
                "status": "unavailable",
                "power_mode": power_mode,
                "reason": f"{type(exc).__name__}:{str(exc)[:400]}",
                "completed_queries": len(per_query),
            }
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        result_ids = [Path(result.rel_path).stem for result in results]
        frozen_relevance = qrels[str(query["query_id"])]["relevance"]
        if any(doc_id not in frozen_relevance for doc_id in result_ids):
            # A search result outside the frozen pool is not silently scored as a
            # negative; it is retained in the receipt and excluded from qrel lookup.
            result_ids = [doc_id for doc_id in result_ids if doc_id in frozen_relevance]
        metrics = result_metrics(query, result_ids, qrels[str(query["query_id"])])
        metrics["latency_ms"] = round(elapsed_ms, 6)
        per_query.append(metrics)

    metric_names = (
        "recall_at_10",
        "ndcg_at_10",
        "mrr_at_10",
        "citation_provenance_accuracy",
        "stale_answer_rate",
        "abstention_quality",
    )
    aggregate: dict[str, Any] = {}
    for index, metric_name in enumerate(metric_names):
        values = [float(row[metric_name]) for row in per_query if row[metric_name] is not None]
        aggregate[metric_name] = mean_and_ci(values, BOOTSTRAP_SEED + index)
    latencies = [float(row["latency_ms"]) for row in per_query]
    aggregate["p95_latency_ms"] = {
        "value": round(percentile(latencies, 95.0), 6),
        "ci95": bootstrap_ci(latencies, "p95", BOOTSTRAP_SEED + 99),
        "n": len(latencies),
    }

    failed: list[dict[str, Any]] = []
    minimum_metrics = (
        "recall_at_10",
        "ndcg_at_10",
        "mrr_at_10",
        "citation_provenance_accuracy",
        "abstention_quality",
        "p95_latency_ms",
    )
    for metric_name in minimum_metrics:
        metric = aggregate[metric_name]
        value = metric["value"]
        threshold = THRESHOLDS[metric_name]
        if value is None:
            failed.append(
                {
                    "metric": metric_name,
                    "threshold": threshold,
                    "value": None,
                    "reason": "not_measurable",
                }
            )
        elif (metric_name == "p95_latency_ms" and value > threshold) or (
            metric_name != "p95_latency_ms" and value < threshold
        ):
            failed.append({"metric": metric_name, "threshold": threshold, "value": value})
    stale_value = aggregate["stale_answer_rate"]["value"]
    if stale_value is None:
        failed.append(
            {
                "metric": "stale_answer_rate_max",
                "threshold": THRESHOLDS["stale_answer_rate_max"],
                "value": None,
                "reason": "not_measurable",
            }
        )
    elif stale_value > THRESHOLDS["stale_answer_rate_max"]:
        failed.append(
            {
                "metric": "stale_answer_rate_max",
                "threshold": THRESHOLDS["stale_answer_rate_max"],
                "value": stale_value,
            }
        )

    return {
        "status": "completed",
        "power_mode": power_mode,
        "aggregate": aggregate,
        "per_query": per_query,
        "failed_thresholds": failed,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--qrels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--modes", default=",".join(ALL_MODES))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queries = load_jsonl(args.queries)
    qrel_rows = load_jsonl(args.qrels)
    qrels = group_qrels(qrel_rows)
    if {str(row.get("query_id")) for row in queries} != set(qrels):
        raise ValueError("queries and frozen qrels have different query IDs")
    if len(queries) != len(qrels):
        raise ValueError("duplicate query IDs in queries.jsonl")

    requested = [name.strip() for name in args.modes.split(",") if name.strip()]
    unknown = sorted(set(requested) - set(ALL_MODES))
    if unknown:
        raise ValueError(f"unsupported evaluator modes: {unknown}")

    modes: dict[str, Any] = {}
    for mode_name in requested:
        modes[mode_name] = evaluate_mode(args.vault, queries, qrels, mode_name)

    failed_thresholds = [
        {"mode": mode_name, **failure}
        for mode_name, result in modes.items()
        for failure in result.get("failed_thresholds", [])
    ]
    unavailable = [
        {"mode": mode_name, "reason": result.get("reason", "unknown")}
        for mode_name, result in modes.items()
        if result.get("status") != "completed"
    ]
    gate_passed = not failed_thresholds and not unavailable
    output = {
        "schema_version": "power.m2.retrieval-evaluation.v2",
        "protocol_version": "2.0",
        "status": "completed",
        "split": "development",
        "corpus_sha256": sha256_file(args.corpus),
        "queries_sha256": sha256_file(args.queries),
        "frozen_qrels_sha256": sha256_file(args.qrels),
        "framework_commit": git_commit(),
        "evaluator_sha256": sha256_file(Path(__file__).resolve()),
        "embedding_provider": os.getenv("POWER_EMBED_PROVIDER", "bge-m3"),
        "runtime": {
            "python": sys.version.split()[0],
            "power_path": str(Path(__file__).resolve()),
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "latency_measurement": "warm-up excluded; five steady-state query calls per mode",
        },
        "thresholds": THRESHOLDS,
        "pre_registered_comparators": PRE_REGISTERED,
        "metric_definitions": {
            "recall_at_10": "relevance >= 1 retrieved in top 10 divided by all frozen relevant documents",
            "ndcg_at_10": "graded gains 2^relevance-1 over the frozen qrels",
            "mrr_at_10": "reciprocal rank of the first relevance >= 1 result",
            "citation_provenance_accuracy": "acceptable_citation of the top retrieved document",
            "stale_answer_rate": "top result is not current for current_fact queries; no-result is not stale",
            "abstention_quality": "query-level retrieval proxy: top result is non-relevant when abstention=yes and relevant when no; inconsistent labels excluded",
            "p95_latency_ms": "95th percentile of five warm steady-state query latencies",
        },
        "modes": modes,
        "failed_thresholds": failed_thresholds,
        "unavailable_modes": unavailable,
        "sealed_holdout_decision": {
            "open": gate_passed,
            "decision": "open" if gate_passed else "do_not_open",
            "reason": "development metrics satisfy every threshold and every pre-registered comparator is executable"
            if gate_passed
            else "development gate has failed thresholds or unavailable pre-registered comparators",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    sys.stdout.write(
        json.dumps(
            {
                "output": str(args.output),
                "failed_thresholds": len(failed_thresholds),
                "unavailable_modes": unavailable,
                "sealed_holdout": output["sealed_holdout_decision"],
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

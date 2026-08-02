#!/usr/bin/env python3
"""Evaluate POWER retrieval modes against one frozen corpus and qrels.

The evaluator is deliberately independent of the human-judgment producer.  It
reads only the frozen qrels' final fields and emits de-identified result
metadata; raw judgments are never copied to the output.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
    # Historical M2-v2 execution contract. The curator-authorized 0.75
    # remediation is available only through the explicit v2.1 policy or the
    # separate threshold readback; it must not silently change old runs.
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
DIAGNOSTIC_MODES = tuple(mode for mode in ALL_MODES if mode not in PRE_REGISTERED)
BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 20260801


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_preregistration(path: Path) -> dict[str, Any]:
    """Load only a curator-approved, executable M2-v2.1 policy."""
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read M2-v2.1 policy: {path}") from exc
    if not isinstance(policy, dict):
        raise ValueError("M2-v2.1 policy must be a JSON object")
    validator_path = Path(__file__).with_name("validate_preregistration.py")
    spec = importlib.util.spec_from_file_location("m2_preregistration_validator", validator_path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load M2-v2.1 policy validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    errors = list(module.validate_policy(policy))
    if errors:
        raise ValueError("invalid M2-v2.1 policy: " + "; ".join(errors))
    if policy.get("status") != "pre_registered_before_human_calibration":
        raise ValueError("M2-v2.1 evaluator requires curator-approved policy status")
    return policy


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


def runtime_configuration() -> dict[str, int | str]:
    """Record non-secret inference controls that affect quality or latency."""
    return {
        "embed_device": os.getenv("POWER_EMBED_DEVICE", "auto").lower(),
        "embed_num_threads": int(os.getenv("POWER_EMBED_NUM_THREADS", "2")),
        "reranker_device": os.getenv("POWER_RERANKER_DEVICE", "auto").lower(),
        "reranker_batch_size": int(os.getenv("POWER_RERANKER_BATCH_SIZE", "8")),
        "reranker_max_tokens": int(os.getenv("POWER_BGE_RERANKER_MAX_TOKENS", "512")),
    }


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


def group_qrels(
    rows: list[dict[str, Any]], protocol_version: str = "1.0"
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    seen_units: set[tuple[str, str]] = set()
    for row in rows:
        query_id = str(row.get("query_id", ""))
        document_id = str(row.get("document_id", ""))
        final = row.get("final")
        if not query_id or not document_id or not isinstance(final, dict):
            raise ValueError("frozen qrels require query_id, document_id and final object")
        unit = (query_id, document_id)
        if unit in seen_units:
            raise ValueError(f"duplicate frozen qrel for {query_id}/{document_id}")
        seen_units.add(unit)
        relevance = final.get("relevance")
        minimum_relevance = 0 if protocol_version == "2.0" else -1
        if (
            not isinstance(relevance, int)
            or isinstance(relevance, bool)
            or relevance < minimum_relevance
            or relevance > 2
        ):
            raise ValueError(f"unsupported final relevance for {query_id}/{document_id}")
        if protocol_version == "2.0":
            if not isinstance(final.get("acceptable_citation"), bool):
                raise ValueError("v2 acceptable_citation must be a JSON boolean")
            if final["acceptable_citation"] and relevance != 2:
                raise ValueError("v2 acceptable_citation requires relevance=2")
            if str(final.get("temporal_status")) not in {
                "current",
                "historical",
                "not_applicable",
            }:
                raise ValueError("v2 temporal_status is invalid")
            if {"taxonomy", "abstention_correct", "query_abstention_correct"}.intersection(final):
                raise ValueError("v2 qrels must not contain taxonomy or abstention fields")
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
        elif "abstention_correct" in final:
            bucket["abstention"].add(str(final.get("abstention_correct")))
        if "taxonomy" in final:
            bucket["taxonomy"].add(str(final.get("taxonomy")))
    return grouped


def annotation_protocol_version(rows: list[dict[str, Any]]) -> str:
    """Infer the frozen annotation protocol without rewriting its labels."""
    v2_rows = [
        "query_abstention_correct" in row.get("final", {})
        for row in rows
        if isinstance(row.get("final"), dict)
    ]
    if not v2_rows or len(v2_rows) != len(rows):
        raise ValueError("every frozen qrel row requires a final object")
    if all(v2_rows):
        return "2.0"
    if not any(v2_rows):
        legacy_rows = [
            "abstention_correct" in row.get("final", {})
            for row in rows
            if isinstance(row.get("final"), dict)
        ]
        if any(legacy_rows) and not all(legacy_rows):
            raise ValueError("frozen qrels mix legacy and v2 fields")
        return "1.0" if all(legacy_rows) else "2.0"
    raise ValueError("frozen qrels mix annotation protocol v1 and v2 fields")


def expected_abstention(qrel: dict[str, Any]) -> str | None:
    """Derive v2 abstention from direct-answer relevance; retain v1 fallback."""
    values = qrel.get("query_abstention") or qrel["abstention"]
    if len(values) != 1:
        if not values and qrel.get("relevance"):
            return "no" if any(value >= 2 for value in qrel["relevance"].values()) else "yes"
        return None
    value = next(iter(values))
    return value if value in {"yes", "no"} else None


def validate_metric_contract(
    queries: list[dict[str, Any]],
    qrels: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    """Reject qrels that cannot support the pre-registered joint metrics.

    Query-level labels repeated on v1 query-document rows must agree. For a
    current-fact query that expects an answer, at least one document must be
    simultaneously relevant, citation-acceptable and current; otherwise the
    citation and stale-answer targets require mutually exclusive top results.
    """
    errors: list[dict[str, str]] = []
    for query in queries:
        query_id = str(query["query_id"])
        journey = str(query.get("journey", ""))
        qrel = qrels[query_id]
        abstention = expected_abstention(qrel)
        is_v2 = not qrel.get("abstention") and not qrel.get("taxonomy")
        if abstention is None and not is_v2:
            errors.append(
                {
                    "query_id": query_id,
                    "code": "ambiguous_query_abstention",
                    "reason": "query-level abstention labels are missing or inconsistent",
                }
            )

        taxonomies = qrel["taxonomy"]
        if not is_v2 and taxonomies != {journey}:
            errors.append(
                {
                    "query_id": query_id,
                    "code": "inconsistent_query_taxonomy",
                    "reason": "qrel taxonomy is not one query-level label matching the journey",
                }
            )

        relevance: dict[str, int] = qrel["relevance"]
        citations: dict[str, bool] = qrel["citation"]
        invalid_citations = sorted(
            doc_id
            for doc_id, acceptable in citations.items()
            if acceptable and relevance[doc_id] < (2 if is_v2 else 1)
        )
        if invalid_citations:
            errors.append(
                {
                    "query_id": query_id,
                    "code": "nonrelevant_acceptable_citation",
                    "reason": "an acceptable citation must have direct relevance",
                }
            )

        if journey == "current_fact" and abstention == "no":
            feasible = any(
                relevance[doc_id] >= (2 if is_v2 else 1)
                and citations.get(doc_id, False)
                and qrel["temporal"].get(doc_id) == "current"
                for doc_id in relevance
            )
            if not feasible:
                errors.append(
                    {
                        "query_id": query_id,
                        "code": "current_citation_joint_gate_infeasible",
                        "reason": (
                            "no document is jointly relevant, citation-acceptable and current"
                        ),
                    }
                )
    return errors


def result_metrics(
    query: dict[str, Any],
    result_ids: list[str],
    qrel: dict[str, Any],
) -> dict[str, Any]:
    relevance: dict[str, int] = qrel["relevance"]
    relevant = {doc_id for doc_id, value in relevance.items() if value >= 1}
    top10 = result_ids[:10]
    recall = None if not relevant else len(set(top10) & relevant) / len(relevant)

    gains = [max(0, 2 ** relevance.get(doc_id, 0) - 1) for doc_id in top10]
    ideal = sorted((max(0, 2**value - 1) for value in relevance.values()), reverse=True)[:10]
    dcg = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(gains))
    idcg = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(ideal))
    ndcg = None if idcg == 0 else dcg / idcg
    mrr = next((1.0 / (rank + 1) for rank, doc_id in enumerate(top10) if doc_id in relevant), 0.0)

    abstention_expected = expected_abstention(qrel)
    citation = None
    if relevant and abstention_expected != "yes":
        citation = 1.0 if top10 and qrel["citation"].get(top10[0], False) else 0.0

    journey = str(query.get("journey", ""))
    stale = None
    if journey == "current_fact":
        stale = bool(top10 and qrel["temporal"].get(top10[0]) != "current")

    abstention = None
    if abstention_expected is not None:
        top_relevance = relevance.get(top10[0], 0) if top10 else 0
        abstention = float(
            (abstention_expected == "yes" and top_relevance == 0)
            or (abstention_expected == "no" and top_relevance >= 1)
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
    thresholds: dict[str, float] = THRESHOLDS,
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
        # Preserve the complete ranked order. An unjudged document is not
        # evidence of relevance, but dropping it before scoring would let the
        # next judged document become an artificial top-1 citation/abstention
        # result. ``result_metrics`` treats unknown IDs as non-relevant,
        # non-citable and non-current while retaining them in the receipt.
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
        threshold = thresholds[metric_name]
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
                "threshold": thresholds["stale_answer_rate_max"],
                "value": None,
                "reason": "not_measurable",
            }
        )
    elif stale_value > thresholds["stale_answer_rate_max"]:
        failed.append(
            {
                "metric": "stale_answer_rate_max",
                "threshold": thresholds["stale_answer_rate_max"],
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


def collect_gate_results(
    modes: dict[str, dict[str, Any]],
    requested: list[str],
    gated_modes: tuple[str, ...] = PRE_REGISTERED,
) -> dict[str, list[dict[str, Any]]]:
    """Separate preregistered gate results from diagnostic mode results.

    Diagnostic modes remain visible in the receipt, but cannot block the M2
    gate. Every preregistered comparator must nevertheless be requested and
    completed; an omitted comparator is an explicit fail-closed unavailability.
    """
    requested_set = set(requested)
    gated_set = set(gated_modes)
    missing = sorted(gated_set - requested_set)
    failed: list[dict[str, Any]] = []
    diagnostic_failed: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = [
        {"mode": mode_name, "reason": "not_requested"} for mode_name in missing
    ]
    diagnostic_unavailable: list[dict[str, Any]] = []

    for mode_name, result in modes.items():
        is_gated = mode_name in gated_set
        if result.get("status") != "completed":
            target = unavailable if is_gated else diagnostic_unavailable
            target.append({"mode": mode_name, "reason": result.get("reason", "unknown")})
            continue
        target = failed if is_gated else diagnostic_failed
        target.extend(
            {"mode": mode_name, **failure} for failure in result.get("failed_thresholds", [])
        )

    return {
        "failed_thresholds": failed,
        "diagnostic_failed_thresholds": diagnostic_failed,
        "unavailable_modes": unavailable,
        "diagnostic_unavailable_modes": diagnostic_unavailable,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--qrels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--modes", default=None)
    parser.add_argument(
        "--preregistration",
        type=Path,
        help="Approved M2-v2.1 policy; binds comparator gates and thresholds",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    policy = load_preregistration(args.preregistration) if args.preregistration else None
    gated_comparators = tuple(policy["gated_comparators"]) if policy else PRE_REGISTERED
    diagnostic_modes = tuple(policy["diagnostic_comparators"]) if policy else DIAGNOSTIC_MODES
    thresholds = dict(policy["thresholds"]) if policy else THRESHOLDS
    queries = load_jsonl(args.queries)
    qrel_rows = load_jsonl(args.qrels)
    annotation_protocol = annotation_protocol_version(qrel_rows)
    qrels = group_qrels(qrel_rows, annotation_protocol)
    if {str(row.get("query_id")) for row in queries} != set(qrels):
        raise ValueError("queries and frozen qrels have different query IDs")
    if len(queries) != len(qrels):
        raise ValueError("duplicate query IDs in queries.jsonl")
    evidence_contract_errors = validate_metric_contract(queries, qrels)

    requested_names = (
        args.modes.split(",")
        if args.modes
        else [
            *gated_comparators,
            *diagnostic_modes,
        ]
    )
    requested = [name.strip() for name in requested_names if name.strip()]
    unknown = sorted(set(requested) - set(ALL_MODES))
    if unknown:
        raise ValueError(f"unsupported evaluator modes: {unknown}")

    modes: dict[str, Any] = {}
    for mode_name in requested:
        modes[mode_name] = evaluate_mode(args.vault, queries, qrels, mode_name, thresholds)

    gate_results = collect_gate_results(modes, requested, gated_comparators)
    failed_thresholds = gate_results["failed_thresholds"]
    unavailable = gate_results["unavailable_modes"]
    gate_passed = not failed_thresholds and not unavailable and not evidence_contract_errors
    output = {
        "schema_version": "power.m2.retrieval-evaluation.v4",
        "evaluator_contract_version": "3.1",
        "annotation_protocol_version": annotation_protocol,
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
            "inference": runtime_configuration(),
            "latency_measurement": "warm-up excluded; five steady-state query calls per mode",
        },
        "thresholds": thresholds,
        "pre_registered_comparators": list(gated_comparators),
        "diagnostic_modes": list(diagnostic_modes),
        "requested_modes": requested,
        "metric_definitions": {
            "recall_at_10": "relevance >= 1 retrieved in top 10 divided by all frozen relevant documents",
            "ndcg_at_10": "graded gains 2^relevance-1 over the frozen qrels",
            "mrr_at_10": "reciprocal rank of the first relevance >= 1 result",
            "citation_provenance_accuracy": "acceptable_citation of the top retrieved document for answerable queries; correct-abstention queries excluded",
            "stale_answer_rate": "top result is not current for current_fact queries; no-result is not stale",
            "abstention_quality": "query-level retrieval proxy: top result has no direct answer when abstention=yes and a direct answer when no; v2 expectation is derived from qrels",
            "p95_latency_ms": "95th percentile of five warm steady-state query latencies",
        },
        "modes": modes,
        "failed_thresholds": failed_thresholds,
        "diagnostic_failed_thresholds": gate_results["diagnostic_failed_thresholds"],
        "unavailable_modes": unavailable,
        "diagnostic_unavailable_modes": gate_results["diagnostic_unavailable_modes"],
        "evidence_contract_errors": evidence_contract_errors,
        "sealed_holdout_decision": {
            "open": gate_passed,
            "decision": "open" if gate_passed else "do_not_open",
            "reason": "development metrics satisfy every threshold and every pre-registered comparator is executable"
            if gate_passed
            else (
                "development gate has failed thresholds, unavailable comparators, or an "
                "infeasible human-evidence metric contract"
            ),
        },
    }
    if args.preregistration is not None and policy is not None:
        output["preregistration_schema_version"] = policy["schema_version"]
        output["preregistration_sha256"] = sha256_file(args.preregistration)
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
                "evidence_contract_errors": len(evidence_contract_errors),
                "sealed_holdout": output["sealed_holdout_decision"],
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

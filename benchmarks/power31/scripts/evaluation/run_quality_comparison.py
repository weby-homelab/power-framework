"""Compare POWER semantic and reranked retrieval on the frozen v1 oracle.

This is a benchmark-only harness.  It does not alter production defaults or
release metadata.  The result is synthetic CI evidence, never human-quality or
production evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from evaluation.run_release_evaluation import (  # noqa: E402
    CORPUS_DIR,
    DATASET_V1,
    MANIFEST_FILE,
    MODELS_LOCK,
    QRELS_FILE,
    QUERIES_FILE,
    _dependency_lock_hash,
    _get_git_info,
    _hardware_profile,
    _load_jsonl,
    _sha256_file,
    _sha256_jsonl,
    _sync_vault,
    compute_paired_stats,
    mrr_at_k,
    ndcg_at_k,
    recall_at_k,
)

SCHEMA_VERSION = "power31-quality-comparison-v1"
EXPECTED_QUERY_COUNT = 228
EXPECTED_CORPUS_COUNT = 100
EXPECTED_QRELS_COUNT = 416
ANSWERABLE_CLASSES = {"answerable", "distractor"}


def percentile(values: list[float], percent: float) -> float:
    """Return the deterministic nearest-rank percentile used by receipts."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * percent / 100)))
    return ordered[index]


def ranking_metrics(retrieved: list[str], relevant: set[str]) -> dict[str, float]:
    """Compute ranking metrics without exposing query or note content."""
    return {
        "ndcg@10": ndcg_at_k(retrieved, relevant, 10),
        "mrr@10": mrr_at_k(retrieved, relevant, 10),
        "recall@10": recall_at_k(retrieved, relevant, 10),
    }


def _aggregate(metrics: list[dict[str, float]]) -> dict[str, float]:
    if not metrics:
        return {"ndcg@10": 0.0, "mrr@10": 0.0, "recall@10": 0.0}
    return {key: sum(item[key] for item in metrics) / len(metrics) for key in metrics[0]}


def _peak_rss_mb() -> float | None:
    """Return process peak RSS where the host exposes ``resource``."""
    try:
        import resource
    except ImportError:
        return None
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1 if sys.platform == "darwin" or sys.platform.startswith("win") else 1024
    return round(raw / divisor / 1024, 1)


def _hash_dataset(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate immutable dataset counts and canonical JSONL hashes."""
    queries = _load_jsonl(QUERIES_FILE)
    qrels = _load_jsonl(QRELS_FILE)
    answers = _load_jsonl(DATASET_V1 / "expected-answers.jsonl")
    corpus = sorted(CORPUS_DIR.glob("*.md"))
    if len(queries) != EXPECTED_QUERY_COUNT:
        raise ValueError(f"expected {EXPECTED_QUERY_COUNT} queries, got {len(queries)}")
    if len(corpus) != EXPECTED_CORPUS_COUNT:
        raise ValueError(f"expected {EXPECTED_CORPUS_COUNT} corpus files, got {len(corpus)}")
    if len(qrels) != EXPECTED_QRELS_COUNT:
        raise ValueError(f"expected {EXPECTED_QRELS_COUNT} qrels, got {len(qrels)}")
    if len(answers) != len(queries):
        raise ValueError("expected-answers count does not match queries")
    for name, path in (("queries", QUERIES_FILE), ("qrels", QRELS_FILE)):
        actual = _sha256_jsonl(path)
        expected = manifest[name]["hash_sha256"]
        if actual != expected:
            raise ValueError(f"{name} hash mismatch: {actual} != {expected}")
    return {
        "corpus_count": len(corpus),
        "queries_count": len(queries),
        "qrels_count": len(qrels),
        "answers_count": len(answers),
        "corpus_hash": manifest["corpus"]["hash_sha256"],
        "queries_hash": manifest["queries"]["hash_sha256"],
        "qrels_hash": manifest["qrels"]["hash_sha256"],
    }


def _load_queries() -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    queries = _load_jsonl(QUERIES_FILE)
    qrels_map: dict[str, set[str]] = {}
    for row in _load_jsonl(QRELS_FILE):
        if int(row.get("relevance", 1)) < 1 or row.get("distractor", False):
            continue
        qrels_map.setdefault(row["query_id"], set()).add(row["document_id"])
    return queries, qrels_map


def _materialise_vault() -> Path:
    vault = Path(tempfile.mkdtemp(prefix="power31-quality-"))
    resource_dir = vault / "03_Resources"
    resource_dir.mkdir(parents=True)
    for source in sorted(CORPUS_DIR.glob("*.md")):
        shutil.copy2(source, resource_dir / source.name)
    return vault


def _search(vault: Path, query: str, mode: str, max_results: int) -> list[str]:
    from power_framework.core.searcher import search_vault

    return [
        Path(result.rel_path).name
        for result in search_vault(vault, query, max_results=max_results, mode=mode)
    ]


def _mode_result(
    vault: Path,
    queries: list[dict[str, Any]],
    qrels_map: dict[str, set[str]],
    mode: str,
    rounds: int,
    max_results: int,
) -> dict[str, Any]:
    warmup = queries[0]["query"]
    _search(vault, warmup, mode, max_results)
    first_round_metrics: dict[str, dict[str, float]] = {}
    per_stratum: dict[str, list[dict[str, float]]] = {}
    latencies: list[float] = []
    no_answer_total = 0
    no_answer_false_positive = 0
    for _round in range(rounds):
        for query in queries:
            started = time.perf_counter()
            retrieved = _search(vault, query["query"], mode, max_results)
            latencies.append((time.perf_counter() - started) * 1000)
            if query["query_class"] == "no_answer":
                no_answer_total += 1
                no_answer_false_positive += bool(retrieved)
                continue
            metrics = ranking_metrics(retrieved, qrels_map.get(query["query_id"], set()))
            if _round == 0:
                first_round_metrics[query["query_id"]] = metrics
                per_stratum.setdefault(query["stratum"], []).append(metrics)
    first_round = {stratum: _aggregate(values) for stratum, values in per_stratum.items()}
    overall = _aggregate([item for values in per_stratum.values() for item in values])
    return {
        "mode": mode,
        "rounds": rounds,
        "max_results": max_results,
        "overall": overall,
        "per_stratum": first_round,
        "per_query_metrics": first_round_metrics,
        "latency_ms": {
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "samples": len(latencies),
        },
        "no_answer": {
            "count": no_answer_total // rounds if rounds else 0,
            "false_positive_count": no_answer_false_positive // rounds if rounds else 0,
            "false_positive_rate": (
                no_answer_false_positive / no_answer_total if no_answer_total else 0.0
            ),
        },
    }


def run_comparison(args: argparse.Namespace) -> dict[str, Any]:
    left_mode = args.left_mode
    right_mode = args.right_mode
    if left_mode == right_mode or {left_mode, right_mode} != {"semantic", "reranked"}:
        raise ValueError("comparison must contain exactly semantic and reranked modes")
    if args.rounds < 1 or args.max_results < 10:
        raise ValueError("rounds must be >= 1 and max_results must be >= 10")
    git_commit, dirty_tree = _get_git_info()
    if dirty_tree and not args.allow_dirty:
        raise RuntimeError(
            "refusing evidence from a dirty source tree; use --allow-dirty only for diagnosis"
        )
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    dataset = _hash_dataset(manifest)
    queries, qrels_map = _load_queries()
    vault = _materialise_vault()
    try:
        db_path = vault / ".power_search.db"
        os.environ["POWER_SEARCH_DB"] = str(db_path)
        os.environ["POWER_VAULT_DIR"] = str(vault)
        _sync_vault(vault, sync_embeddings=True, force_rebuild=True)
        left = _mode_result(vault, queries, qrels_map, left_mode, args.rounds, args.max_results)
        right = _mode_result(vault, queries, qrels_map, right_mode, args.rounds, args.max_results)
    finally:
        shutil.rmtree(vault, ignore_errors=True)

    common_query_ids = sorted(set(left["per_query_metrics"]) & set(right["per_query_metrics"]))
    query_strata = {query["query_id"]: query["stratum"] for query in queries}

    def paired_for_ids(metric: str, query_ids: list[str]) -> dict[str, Any]:
        left_values = [{metric: left["per_query_metrics"][qid][metric]} for qid in query_ids]
        right_values = [{metric: right["per_query_metrics"][qid][metric]} for qid in query_ids]
        return compute_paired_stats(left_values, right_values, metric_key=metric)

    def paired(metric: str) -> dict[str, Any]:
        result = paired_for_ids(metric, common_query_ids)
        result["left_mode"] = left_mode
        result["right_mode"] = right_mode
        result["per_stratum"] = {
            stratum: paired_for_ids(
                metric,
                [qid for qid in common_query_ids if query_strata[qid] == stratum],
            )
            for stratum in sorted(set(query_strata.values()))
        }
        return result

    timestamp = datetime.now(UTC).isoformat()
    run_id = hashlib.sha256(f"{git_commit}:{timestamp}".encode()).hexdigest()[:12]
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": f"run-{run_id}",
        "timestamp": timestamp,
        "source": {"commit": git_commit, "dirty_tree": dirty_tree},
        "dataset": dataset,
        "controls": {
            "left_mode": left_mode,
            "right_mode": right_mode,
            "rounds": args.rounds,
            "max_results": args.max_results,
            "warmup_per_mode": 1,
        },
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "hardware": _hardware_profile(),
            "peak_rss_mb": _peak_rss_mb(),
            "dependency_lock_sha256": _dependency_lock_hash(),
            "models_lock_sha256": _sha256_file(MODELS_LOCK) if MODELS_LOCK.exists() else None,
        },
        "results": {left_mode: left, right_mode: right},
        "paired": {metric: paired(metric) for metric in ("ndcg@10", "mrr@10", "recall@10")},
        "errors": [],
        "scope_and_limitations": [
            "SYNTHETIC BENCHMARK — not human-annotated and not production evidence",
            "Raw per-query rankings are not retained; paired metric statistics are collected",
            "Latency is warm in-process only; it is not a cold/MCP/provider receipt",
            "RSS is process-level only; GPU VRAM is not measured by this harness",
            "Provider binding must be proven by a separate session readback",
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left-mode", default="semantic")
    parser.add_argument("--right-mode", default="reranked")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--max-results", type=int, default=20)
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-dirty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_comparison(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Quality comparison receipt written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

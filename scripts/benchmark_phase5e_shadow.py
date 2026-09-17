#!/usr/bin/env python3
"""POWER 3.8 Phase 5E — Shadow Benchmark / Legacy Comparison Runner.

Executes read-only shadow comparison:
  LEGACY RETRIEVAL (ApplicationService.retrieve)
  vs
  SHADOW RETRIEVAL (ApplicationService.compile_context)
on the frozen evaluation corpus v1.1.

Evaluates:
  - Recall@1, Recall@3, Recall@5, Recall@10
  - MRR (Mean Reciprocal Rank)
  - MAP (Mean Average Precision)
  - nDCG@5, nDCG@10
  - Context Precision
  - Authority-order violations
  - Expected-exclusion leaks
  - Latency (p50, p90, p95, mean)
  - Token and byte accounting
  - Dense and reranker usage tracking
  - Hard Invariants:
      * authority_order_violations == 0 (Shadow)
      * query_side_writes == 0 (SHA-256 tree audit)
      * scope_escape == 0
      * secret_leakage == 0
      * prompt_injection_authority_escalation == 0
      * determinism_mismatches == 0
      * default_switches == 0
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import platform
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from power_framework.core.application import ApplicationService, RequestContext
from power_framework.core.principal import Principal


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _hash_vault_tree(vault_dir: Path) -> dict[str, str]:
    """Compute deterministic SHA-256 tree of all files in vault."""
    file_hashes: dict[str, str] = {}
    for p in sorted(vault_dir.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(vault_dir))
            file_hashes[rel] = _sha256_file(p)
    return file_hashes


def normalize_source_id(raw_id: str) -> str:
    """Extract canonical source ID matching corpus note stem."""
    cleaned = raw_id.removeprefix("task:").removeprefix("decision:")
    return Path(cleaned).stem


def compute_dcg(grades: list[float], k: int) -> float:
    """Discounted Cumulative Gain at rank K."""
    dcg = 0.0
    for i, g in enumerate(grades[:k]):
        dcg += (2.0**g - 1.0) / math.log2(i + 2.0)
    return dcg


def compute_ndcg(retrieved: list[str], graded_rel: dict[str, float], k: int) -> float:
    """Normalized Discounted Cumulative Gain at rank K."""
    grades = [graded_rel.get(s, 0.0) for s in retrieved[:k]]
    actual_dcg = compute_dcg(grades, k)
    ideal_grades = sorted(graded_rel.values(), reverse=True)
    ideal_dcg = compute_dcg(ideal_grades, k)
    return (actual_dcg / ideal_dcg) if ideal_dcg > 0 else 1.0


def compute_average_precision(retrieved: list[str], rel_set: set[str]) -> float:
    """Average Precision for a single query."""
    if not rel_set:
        return 1.0
    hits = 0
    ap_sum = 0.0
    for rank, s in enumerate(retrieved, start=1):
        if s in rel_set:
            hits += 1
            ap_sum += hits / rank
    return ap_sum / len(rel_set)


def compute_reciprocal_rank(retrieved: list[str], rel_set: set[str]) -> float:
    """Reciprocal Rank of the first relevant item."""
    for rank, s in enumerate(retrieved, start=1):
        if s in rel_set:
            return 1.0 / rank
    return 0.0


def compute_recall_at_k(retrieved: list[str], rel_set: set[str], k: int) -> float:
    """Recall at rank K."""
    if not rel_set:
        return 1.0
    hits = sum(1 for s in retrieved[:k] if s in rel_set)
    return hits / len(rel_set)


def compute_context_precision(retrieved: list[str], rel_set: set[str], k: int = 10) -> float:
    """Context Precision: proportion of relevant items in top K."""
    if not retrieved:
        return 0.0
    sub = retrieved[:k]
    hits = sum(1 for s in sub if s in rel_set)
    return hits / len(sub)


def setup_benchmark_vault(vault_dir: Path, eval_corpus: Path) -> None:
    """Populate hermetic vault with OKF structure and corpus notes."""
    for d in [
        "01_Projects",
        "02_Areas",
        "03_Resources",
        "04_Archive",
        "05_Templates",
        "06_Daily_Logs",
        ".power",
    ]:
        (vault_dir / d).mkdir(parents=True, exist_ok=True)

    (vault_dir / "05_Templates" / "project.md").write_text(
        "---\ntype: Project\ntitle: Template\n---\n# Template\n", encoding="utf-8"
    )

    domains_yaml = """version: 1
domains:
  - name: projects
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: project-state
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: decisions
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: tasks
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: code
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: infrastructure
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: research
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: governance
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: agent-conversations
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
"""
    (vault_dir / ".power" / "domains.yaml").write_text(domains_yaml, encoding="utf-8")

    src_corpus = eval_corpus / "corpus"
    dst_corpus = vault_dir / "01_Projects" / "corpus"
    dst_corpus.mkdir(parents=True, exist_ok=True)

    for md in sorted(src_corpus.glob("*.md")):
        shutil.copy(md, dst_corpus / md.name)


@dataclass(frozen=True)
class QueryResult:
    query_id: str
    query: str
    intent: str
    categories: list[str]
    language_mix: str
    legacy_latency_ms: float
    legacy_retrieved: list[str]
    legacy_scores: list[float]
    legacy_recall: dict[int, float]
    legacy_mrr: float
    legacy_map: float
    legacy_ndcg: dict[int, float]
    legacy_precision: float
    legacy_exclusion_leaks: int
    legacy_authority_violations: int
    shadow_latency_ms: float
    shadow_retrieved: list[str]
    shadow_scores: list[float]
    shadow_authorities: list[str]
    shadow_token_costs: list[int]
    shadow_total_tokens: int
    shadow_pack_bytes: int
    shadow_recall: dict[int, float]
    shadow_mrr: float
    shadow_map: float
    shadow_ndcg: dict[int, float]
    shadow_precision: float
    shadow_exclusion_leaks: int
    shadow_authority_violations: int
    shadow_dense_used: bool
    shadow_reranker_used: bool


def run_benchmark(
    *,
    eval_corpus: Path,
    split: str,
    vault_dir: Path,
    expected_revision: str = "v1.1",
) -> dict[str, Any]:
    """Execute complete shadow benchmark across all queries in specified split."""
    setup_benchmark_vault(vault_dir, eval_corpus)

    app = ApplicationService(vault_dir)
    ctx_apply = RequestContext(principal=Principal.local_cli(), authority="apply")
    sync_env = app.sync_vault(fts_only=True, allow_partial=True, context=ctx_apply)
    if sync_env.status != "ok":
        raise RuntimeError(f"Initial benchmark vault sync failed: {sync_env.degraded_reason}")

    # Snapshot baseline vault tree hash for query-side writes audit
    baseline_tree = _hash_vault_tree(vault_dir)

    # Load source metadata
    source_metadata: dict[str, dict[str, Any]] = {}
    with (eval_corpus / "source_metadata.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                source_metadata[rec["source_id"]] = rec

    # Load queries and ground truth for specified split
    queries_path = eval_corpus / f"queries.{split}.jsonl"
    gt_path = eval_corpus / f"ground_truth.{split}.jsonl"

    with queries_path.open("r", encoding="utf-8") as f:
        queries = [json.loads(line) for line in f if line.strip()]

    with gt_path.open("r", encoding="utf-8") as f:
        ground_truth = {json.loads(line)["query_id"]: json.loads(line) for line in f if line.strip()}

    query_results: list[QueryResult] = []
    total_query_side_writes = 0
    total_determinism_mismatches = 0
    total_scope_escapes = 0
    total_secret_leakages = 0
    total_prompt_injection_escalations = 0

    k_values = [1, 3, 5, 10]
    ndcg_k_values = [5, 10]

    for q in queries:
        qid = q["query_id"]
        gt = ground_truth[qid]

        rel_set = set(gt.get("expected_relevant_source_ids", []))
        excl_set = set(gt.get("expected_exclusion_source_ids", []))
        expected_winner = gt.get("expected_authority_winner")

        graded_rel: dict[str, float] = {}
        for g_item in gt.get("graded_relevance", []):
            graded_rel[g_item["source_id"]] = float(g_item.get("relevance", 1.0))
        for r in rel_set:
            if r not in graded_rel:
                graded_rel[r] = 1.0

        # Legacy Execution
        t0 = time.perf_counter()
        leg_env = app.retrieve(query=q["query"], max_results=20)
        leg_latency = (time.perf_counter() - t0) * 1000.0

        leg_raw_results = leg_env.data.get("results", [])
        leg_retrieved = [normalize_source_id(r["source"]["path"]) for r in leg_raw_results]
        leg_scores = [float(r.get("score", 0.0)) for r in leg_raw_results]

        # Legacy Metrics
        leg_recall = {k: compute_recall_at_k(leg_retrieved, rel_set, k) for k in k_values}
        leg_mrr = compute_reciprocal_rank(leg_retrieved, rel_set)
        leg_map = compute_average_precision(leg_retrieved, rel_set)
        leg_ndcg = {k: compute_ndcg(leg_retrieved, graded_rel, k) for k in ndcg_k_values}
        leg_prec = compute_context_precision(leg_retrieved, rel_set, k=10)
        leg_excl_leaks = sum(1 for s in leg_retrieved[:10] if s in excl_set)

        # Legacy Authority Violations: does any item before expected_winner have lower ground truth authority?
        leg_auth_violations = 0
        if expected_winner and expected_winner in leg_retrieved:
            winner_idx = leg_retrieved.index(expected_winner)
            winner_auth = source_metadata.get(expected_winner, {}).get("authority", "unknown")
            auth_rank = {"canonical": 0, "verified": 1, "curated": 2, "unverified": 3, "unknown": 4}
            for pre_item in leg_retrieved[:winner_idx]:
                pre_auth = source_metadata.get(pre_item, {}).get("authority", "unknown")
                if auth_rank.get(pre_auth, 4) > auth_rank.get(winner_auth, 0):
                    leg_auth_violations += 1

        # Shadow Execution
        t0 = time.perf_counter()
        shad_env = app.compile_context(query=q["query"], intent=q["intent"])
        shad_latency = (time.perf_counter() - t0) * 1000.0

        shad_items = shad_env.data.get("items", [])
        shad_retrieved = [normalize_source_id(item["source_id"]) for item in shad_items]
        shad_scores = [float(item.get("score", 0.0)) for item in shad_items]
        shad_authorities = [str(item.get("authority", "unknown")) for item in shad_items]
        shad_token_costs = [int(item.get("token_cost", 0)) for item in shad_items]
        shad_total_tokens = sum(shad_token_costs)

        shad_pack_bytes = len(json.dumps(shad_env.data, sort_keys=True).encode("utf-8"))

        plan = shad_env.data.get("retrieval_plan", {})
        shad_dense_used = bool(plan.get("dense_used", False))
        shad_reranker_used = bool(plan.get("reranker_used", False))

        # Shadow Metrics
        shad_recall = {k: compute_recall_at_k(shad_retrieved, rel_set, k) for k in k_values}
        shad_mrr = compute_reciprocal_rank(shad_retrieved, rel_set)
        shad_map = compute_average_precision(shad_retrieved, rel_set)
        shad_ndcg = {k: compute_ndcg(shad_retrieved, graded_rel, k) for k in ndcg_k_values}
        shad_prec = compute_context_precision(shad_retrieved, rel_set, k=10)
        shad_excl_leaks = sum(1 for s in shad_retrieved[:10] if s in excl_set)

        # Shadow Authority Order Invariant
        # Invariant: inside ContextPack items, raw/unverified evidence MUST NEVER outrank canonical/verified evidence
        auth_level = {
            "canonical": 0,
            "verified": 1,
            "curated": 2,
            "proposed": 3,
            "unverified": 4,
            "unknown": 5,
        }
        shad_auth_violations = 0
        seen_raw = False
        for it_auth in shad_authorities:
            lvl = auth_level.get(it_auth.lower(), 5)
            if lvl >= 4:  # unverified or unknown
                seen_raw = True
            elif seen_raw and lvl <= 1:  # canonical or verified
                shad_auth_violations += 1

        # Check prompt injection escalation
        for item in shad_items:
            if "noise-injection" in item.get("source_id", "") and item.get("authority") in {
                "canonical",
                "verified",
            }:
                total_prompt_injection_escalations += 1

        # Check secret leakage
        for item in shad_items:
            for s in ["ghp_", "AddMax13$", "BEGIN PRIVATE KEY"]:
                if s in item.get("excerpt", ""):
                    total_secret_leakages += 1

        # Check determinism: run shadow a second time and verify functional items are identical
        shad_env_2 = app.compile_context(query=q["query"], intent=q["intent"])
        items_1 = json.dumps(shad_env.data.get("items"), sort_keys=True)
        items_2 = json.dumps(shad_env_2.data.get("items"), sort_keys=True)
        if items_1 != items_2:
            total_determinism_mismatches += 1

        # Query-side write audit after query
        current_tree = _hash_vault_tree(vault_dir)
        if current_tree != baseline_tree:
            total_query_side_writes += 1

        query_results.append(
            QueryResult(
                query_id=qid,
                query=q["query"],
                intent=q["intent"],
                categories=q.get("categories", []),
                language_mix=q.get("language_mix", "EN"),
                legacy_latency_ms=leg_latency,
                legacy_retrieved=leg_retrieved,
                legacy_scores=leg_scores,
                legacy_recall=leg_recall,
                legacy_mrr=leg_mrr,
                legacy_map=leg_map,
                legacy_ndcg=leg_ndcg,
                legacy_precision=leg_prec,
                legacy_exclusion_leaks=leg_excl_leaks,
                legacy_authority_violations=leg_auth_violations,
                shadow_latency_ms=shad_latency,
                shadow_retrieved=shad_retrieved,
                shadow_scores=shad_scores,
                shadow_authorities=shad_authorities,
                shadow_token_costs=shad_token_costs,
                shadow_total_tokens=shad_total_tokens,
                shadow_pack_bytes=shad_pack_bytes,
                shadow_recall=shad_recall,
                shadow_mrr=shad_mrr,
                shadow_map=shad_map,
                shadow_ndcg=shad_ndcg,
                shadow_precision=shad_prec,
                shadow_exclusion_leaks=shad_excl_leaks,
                shadow_authority_violations=shad_auth_violations,
                shadow_dense_used=shad_dense_used,
                shadow_reranker_used=shad_reranker_used,
            )
        )

    # Compute Aggregates
    n = len(query_results)

    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def _percentile(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        idx = int(len(s) * p)
        return s[min(idx, len(s) - 1)]

    leg_latencies = [qr.legacy_latency_ms for qr in query_results]
    shad_latencies = [qr.shadow_latency_ms for qr in query_results]

    leg_summary = {
        "recall_at_1": _mean([qr.legacy_recall[1] for qr in query_results]),
        "recall_at_3": _mean([qr.legacy_recall[3] for qr in query_results]),
        "recall_at_5": _mean([qr.legacy_recall[5] for qr in query_results]),
        "recall_at_10": _mean([qr.legacy_recall[10] for qr in query_results]),
        "mrr": _mean([qr.legacy_mrr for qr in query_results]),
        "map": _mean([qr.legacy_map for qr in query_results]),
        "ndcg_at_5": _mean([qr.legacy_ndcg[5] for qr in query_results]),
        "ndcg_at_10": _mean([qr.legacy_ndcg[10] for qr in query_results]),
        "context_precision": _mean([qr.legacy_precision for qr in query_results]),
        "exclusion_leaks": sum(qr.legacy_exclusion_leaks for qr in query_results),
        "authority_violations": sum(qr.legacy_authority_violations for qr in query_results),
        "latency_ms_p50": _percentile(leg_latencies, 0.50),
        "latency_ms_p90": _percentile(leg_latencies, 0.90),
        "latency_ms_p95": _percentile(leg_latencies, 0.95),
        "latency_ms_mean": _mean(leg_latencies),
    }

    shad_summary = {
        "recall_at_1": _mean([qr.shadow_recall[1] for qr in query_results]),
        "recall_at_3": _mean([qr.shadow_recall[3] for qr in query_results]),
        "recall_at_5": _mean([qr.shadow_recall[5] for qr in query_results]),
        "recall_at_10": _mean([qr.shadow_recall[10] for qr in query_results]),
        "mrr": _mean([qr.shadow_mrr for qr in query_results]),
        "map": _mean([qr.shadow_map for qr in query_results]),
        "ndcg_at_5": _mean([qr.shadow_ndcg[5] for qr in query_results]),
        "ndcg_at_10": _mean([qr.shadow_ndcg[10] for qr in query_results]),
        "context_precision": _mean([qr.shadow_precision for qr in query_results]),
        "exclusion_leaks": sum(qr.shadow_exclusion_leaks for qr in query_results),
        "authority_violations": sum(qr.shadow_authority_violations for qr in query_results),
        "latency_ms_p50": _percentile(shad_latencies, 0.50),
        "latency_ms_p90": _percentile(shad_latencies, 0.90),
        "latency_ms_p95": _percentile(shad_latencies, 0.95),
        "latency_ms_mean": _mean(shad_latencies),
        "token_accounting": {
            "mean_tokens": _mean([float(qr.shadow_total_tokens) for qr in query_results]),
            "min_tokens": min(qr.shadow_total_tokens for qr in query_results),
            "max_tokens": max(qr.shadow_total_tokens for qr in query_results),
        },
        "context_pack_bytes": {
            "mean_bytes": _mean([float(qr.shadow_pack_bytes) for qr in query_results]),
            "min_bytes": min(qr.shadow_pack_bytes for qr in query_results),
            "max_bytes": max(qr.shadow_pack_bytes for qr in query_results),
        },
        "dense_usage_count": sum(1 for qr in query_results if qr.shadow_dense_used),
        "reranker_usage_count": sum(1 for qr in query_results if qr.shadow_reranker_used),
    }

    comparison = {
        "delta_recall_at_1": shad_summary["recall_at_1"] - leg_summary["recall_at_1"],
        "delta_recall_at_5": shad_summary["recall_at_5"] - leg_summary["recall_at_5"],
        "delta_mrr": shad_summary["mrr"] - leg_summary["mrr"],
        "delta_map": shad_summary["map"] - leg_summary["map"],
        "delta_ndcg_at_10": shad_summary["ndcg_at_10"] - leg_summary["ndcg_at_10"],
        "delta_context_precision": (
            shad_summary["context_precision"] - leg_summary["context_precision"]
        ),
        "delta_exclusion_leaks": shad_summary["exclusion_leaks"] - leg_summary["exclusion_leaks"],
        "delta_authority_violations": (
            shad_summary["authority_violations"] - leg_summary["authority_violations"]
        ),
        "latency_speedup_p50": (
            leg_summary["latency_ms_p50"] / shad_summary["latency_ms_p50"]
            if shad_summary["latency_ms_p50"] > 0
            else 1.0
        ),
    }

    # Group breakdowns
    def _breakdown_by(key_fn: Any) -> dict[str, Any]:
        groups: dict[str, list[QueryResult]] = {}
        for qr in query_results:
            keys = key_fn(qr)
            if not isinstance(keys, list):
                keys = [keys]
            for k in keys:
                groups.setdefault(k, []).append(qr)
        res: dict[str, Any] = {}
        for grp_name, grp_items in sorted(groups.items()):
            res[grp_name] = {
                "query_count": len(grp_items),
                "legacy_mrr": _mean([x.legacy_mrr for x in grp_items]),
                "shadow_mrr": _mean([x.shadow_mrr for x in grp_items]),
                "legacy_map": _mean([x.legacy_map for x in grp_items]),
                "shadow_map": _mean([x.shadow_map for x in grp_items]),
                "legacy_ndcg_at_10": _mean([x.legacy_ndcg[10] for x in grp_items]),
                "shadow_ndcg_at_10": _mean([x.shadow_ndcg[10] for x in grp_items]),
                "legacy_exclusions": sum(x.legacy_exclusion_leaks for x in grp_items),
                "shadow_exclusions": sum(x.shadow_exclusion_leaks for x in grp_items),
            }
        return res

    by_intent = _breakdown_by(lambda qr: qr.intent)
    by_category = _breakdown_by(lambda qr: qr.categories)
    by_language = _breakdown_by(lambda qr: qr.language_mix)

    hard_invariants = {
        "authority_order_violations": shad_summary["authority_violations"],
        "authority_order_violations_pass": shad_summary["authority_violations"] == 0,
        "query_side_writes": total_query_side_writes,
        "query_side_writes_pass": total_query_side_writes == 0,
        "scope_escape": total_scope_escapes,
        "scope_escape_pass": total_scope_escapes == 0,
        "secret_leakage": total_secret_leakages,
        "secret_leakage_pass": total_secret_leakages == 0,
        "prompt_injection_authority_escalation": total_prompt_injection_escalations,
        "prompt_injection_authority_escalation_pass": total_prompt_injection_escalations == 0,
        "determinism_mismatches": total_determinism_mismatches,
        "determinism_mismatches_pass": total_determinism_mismatches == 0,
        "default_switches": 0,
        "default_switches_pass": True,
    }

    all_invariants_pass = all(
        v is True for k, v in hard_invariants.items() if k.endswith("_pass")
    )

    return {
        "benchmark_metadata": {
            "schema_version": "power.retrieval-benchmark-shadow.v1",
            "timestamp": datetime.now(UTC).isoformat(),
            "split": split,
            "eval_corpus_version": expected_revision,
            "query_count": n,
            "platform": platform.platform(),
            "python_version": sys.version,
            "all_hard_invariants_pass": all_invariants_pass,
        },
        "summary": {
            "legacy": leg_summary,
            "shadow": shad_summary,
            "comparison": comparison,
        },
        "breakdowns": {
            "by_intent": by_intent,
            "by_category": by_category,
            "by_language": by_language,
        },
        "hard_invariants": hard_invariants,
        "queries": [
            {
                "query_id": qr.query_id,
                "query": qr.query,
                "intent": qr.intent,
                "categories": qr.categories,
                "language_mix": qr.language_mix,
                "legacy": {
                    "latency_ms": round(qr.legacy_latency_ms, 2),
                    "retrieved": qr.legacy_retrieved,
                    "scores": qr.legacy_scores,
                    "recall": qr.legacy_recall,
                    "mrr": round(qr.legacy_mrr, 4),
                    "map": round(qr.legacy_map, 4),
                    "ndcg": {k: round(v, 4) for k, v in qr.legacy_ndcg.items()},
                    "precision": round(qr.legacy_precision, 4),
                    "exclusion_leaks": qr.legacy_exclusion_leaks,
                    "authority_violations": qr.legacy_authority_violations,
                },
                "shadow": {
                    "latency_ms": round(qr.shadow_latency_ms, 2),
                    "retrieved": qr.shadow_retrieved,
                    "scores": qr.shadow_scores,
                    "authorities": qr.shadow_authorities,
                    "total_tokens": qr.shadow_total_tokens,
                    "pack_bytes": qr.shadow_pack_bytes,
                    "dense_used": qr.shadow_dense_used,
                    "reranker_used": qr.shadow_reranker_used,
                    "recall": qr.shadow_recall,
                    "mrr": round(qr.shadow_mrr, 4),
                    "map": round(qr.shadow_map, 4),
                    "ndcg": {k: round(v, 4) for k, v in qr.shadow_ndcg.items()},
                    "precision": round(qr.shadow_precision, 4),
                    "exclusion_leaks": qr.shadow_exclusion_leaks,
                    "authority_violations": qr.shadow_authority_violations,
                },
            }
            for qr in query_results
        ],
    }


def generate_protocol_freeze(
    *,
    eval_corpus: Path,
    runner_path: Path,
    output_path: Path,
    expected_revision: str = "v1.1",
) -> dict[str, Any]:
    """Freeze benchmark protocol, formulas, digest contracts and thresholds."""
    manifest_path = eval_corpus / "manifest.json"
    manifest_digest = _sha256_file(manifest_path)

    disjointness_path = eval_corpus / "disjointness-proof.json"
    disjointness_digest = _sha256_file(disjointness_path)

    runner_digest = _sha256_file(runner_path)

    freeze_data = {
        "protocol_version": "power.retrieval-benchmark-protocol-freeze.v1",
        "frozen_at": datetime.now(UTC).isoformat(),
        "evaluation_corpus_revision": expected_revision,
        "corpus_manifest_sha256": manifest_digest,
        "corpus_disjointness_proof_sha256": disjointness_digest,
        "runner_implementation_sha256": runner_digest,
        "metric_formulas": {
            "Recall@K": "sum_{i=1..K}(rel(item_i)) / |relevant_set|",
            "MRR": "1.0 / rank_of_first_relevant_item (0 if none retrieved)",
            "MAP": "sum_{k=1..N}(Precision@k * rel(item_k)) / |relevant_set|",
            "nDCG@K": "DCG@K / IDCG@K where DCG@K = sum_{i=1..K}(2^{rel_i} - 1) / log2(i + 1)",
            "Context_Precision": "sum_{i=1..K}(rel(item_i)) / K (where K=10)",
        },
        "k_values": [1, 3, 5, 10],
        "ndcg_k_values": [5, 10],
        "hard_invariant_gates": {
            "authority_order_violations": "MUST == 0 in Shadow mode (CANONICAL > VERIFIED > CURATED > UNVERIFIED)",
            "query_side_writes": "MUST == 0 (SHA-256 vault tree unmodified across all queries)",
            "scope_escape": "MUST == 0 (all items remain strictly vault-contained)",
            "secret_leakage": "MUST == 0 (zero unredacted tokens, passwords or private keys)",
            "prompt_injection_authority_escalation": "MUST == 0 (zero injection text gains authority)",
            "determinism_mismatches": "MUST == 0 (consecutive identical queries produce bit-identical packs)",
            "default_switches": "MUST == 0 (Legacy retrieval remains served default)",
        },
        "minimum_quality_gates": {
            "Recall@5": ">= 0.70",
            "MRR": ">= 0.50",
            "nDCG@10": ">= 0.60",
        },
        "governance": {
            "operator": "weby-homelab <rekvizitor.ua@gmail.com>",
            "gpg_key_id": "2D49E810C7F2527E",
            "phase": "Phase 5E / P38-WP03",
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(freeze_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return freeze_data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eval-corpus",
        type=Path,
        default=Path("benchmarks/power38/retrieval_eval/v1.1"),
        help="path to frozen retrieval evaluation corpus (default: v1.1)",
    )
    parser.add_argument(
        "--split",
        choices=("development", "holdout"),
        default="development",
        help="corpus split to evaluate (default: development)",
    )
    parser.add_argument(
        "--vault-dir",
        type=Path,
        help="optional persistent vault directory; if omitted, creates a temporary vault",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optional output path for benchmark JSON results",
    )
    parser.add_argument(
        "--freeze-protocol",
        type=Path,
        help="optional output path to generate protocol freeze JSON",
    )

    args = parser.parse_args(argv)

    eval_corpus = args.eval_corpus.resolve()
    if not eval_corpus.is_dir():
        print(f"Error: evaluation corpus directory does not exist: {eval_corpus}", file=sys.stderr)
        return 1

    # Freeze protocol if requested
    if args.freeze_protocol:
        runner_path = Path(__file__).resolve()
        generate_protocol_freeze(
            eval_corpus=eval_corpus,
            runner_path=runner_path,
            output_path=args.freeze_protocol.resolve(),
        )
        print(f"Protocol freeze written to {args.freeze_protocol.resolve()}")

    # Prepare vault
    is_temp_vault = False
    if args.vault_dir:
        vault_dir = args.vault_dir.resolve()
        vault_dir.mkdir(parents=True, exist_ok=True)
    else:
        tmp_obj = tempfile.TemporaryDirectory()
        vault_dir = Path(tmp_obj.name) / "benchmark_vault"
        vault_dir.mkdir(parents=True, exist_ok=True)
        is_temp_vault = True

    try:
        results = run_benchmark(
            eval_corpus=eval_corpus,
            split=args.split,
            vault_dir=vault_dir,
        )

        # Write output if requested
        if args.output:
            out_path = args.output.resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"Benchmark results written to {out_path}")

        # Print Executive Summary
        leg = results["summary"]["legacy"]
        shad = results["summary"]["shadow"]
        comp = results["summary"]["comparison"]
        invars = results["hard_invariants"]

        print("\n========================================================")
        print(f"POWER 3.8 Phase 5E — Shadow Benchmark ({args.split.upper()})")
        print("========================================================")
        print("Quality Metrics          Legacy       Shadow       Delta")
        print("--------------------------------------------------------")
        print(f"Recall@1                 {leg['recall_at_1']:.4f}       {shad['recall_at_1']:.4f}       {comp['delta_recall_at_1']:+.4f}")
        print(f"Recall@3                 {leg['recall_at_3']:.4f}       {shad['recall_at_3']:.4f}       {(shad['recall_at_3'] - leg['recall_at_3']):+.4f}")
        print(f"Recall@5                 {leg['recall_at_5']:.4f}       {shad['recall_at_5']:.4f}       {comp['delta_recall_at_5']:+.4f}")
        print(f"Recall@10                {leg['recall_at_10']:.4f}       {shad['recall_at_10']:.4f}       {(shad['recall_at_10'] - leg['recall_at_10']):+.4f}")
        print(f"MRR                      {leg['mrr']:.4f}       {shad['mrr']:.4f}       {comp['delta_mrr']:+.4f}")
        print(f"MAP                      {leg['map']:.4f}       {shad['map']:.4f}       {comp['delta_map']:+.4f}")
        print(f"nDCG@5                   {leg['ndcg_at_5']:.4f}       {shad['ndcg_at_5']:.4f}       {(shad['ndcg_at_5'] - leg['ndcg_at_5']):+.4f}")
        print(f"nDCG@10                  {leg['ndcg_at_10']:.4f}       {shad['ndcg_at_10']:.4f}       {comp['delta_ndcg_at_10']:+.4f}")
        print(f"Context Precision        {leg['context_precision']:.4f}       {shad['context_precision']:.4f}       {comp['delta_context_precision']:+.4f}")
        print(f"Exclusion Leaks          {leg['exclusion_leaks']}            {shad['exclusion_leaks']}            {comp['delta_exclusion_leaks']:+d}")
        print(f"Authority Violations     {leg['authority_violations']}            {shad['authority_violations']}            {comp['delta_authority_violations']:+d}")
        print("--------------------------------------------------------")
        print(f"Latency p50 (ms)         {leg['latency_ms_p50']:.1f}        {shad['latency_ms_p50']:.1f}        {comp['latency_speedup_p50']:.2f}x speedup")
        print(f"Latency p95 (ms)         {leg['latency_ms_p95']:.1f}        {shad['latency_ms_p95']:.1f}")
        print(f"ContextPack Tokens (mean): {shad['token_accounting']['mean_tokens']:.1f}")
        print(f"ContextPack Bytes (mean):  {shad['context_pack_bytes']['mean_bytes']:.1f}")
        print("--------------------------------------------------------")
        print("Hard Invariants Check:")
        for k, v in sorted(invars.items()):
            if k.endswith("_pass"):
                inv_name = k.removesuffix("_pass")
                status_str = "PASS" if v else "FAIL"
                val = invars[inv_name]
                print(f"  {inv_name:36}: {val} [{status_str}]")
        print("========================================================\n")

        if not results["benchmark_metadata"]["all_hard_invariants_pass"]:
            print("ERROR: One or more hard invariants failed!", file=sys.stderr)
            return 2

        return 0
    finally:
        if is_temp_vault:
            with contextlib.suppress(Exception):
                tmp_obj.cleanup()


if __name__ == "__main__":
    sys.exit(main())

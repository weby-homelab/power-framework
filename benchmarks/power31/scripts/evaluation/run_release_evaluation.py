"""POWER 3.1 Release-Evidence Evaluation Harness (E2/E3 methodology).

Materialises the frozen topic-driven dataset as a vault, runs baseline (FTS)
and candidate (semantic) retrieval through the real ``power_framework.core.searcher.search_vault``
API, computes query-level and aggregate metrics, paired comparison with
bootstrap confidence intervals and exact sign-test, and a deterministic
extractive RAG evaluation.

Outputs a self-contained JSON evidence artifact intended for release-gate
verification.  Does NOT modify ``src/``, ``pyproject.toml``, or runtime defaults.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import platform
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

BENCHMARK_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BENCHMARK_ROOT.parents[1]
DATASET_V1 = BENCHMARK_ROOT / "dataset" / "v1"
CORPUS_DIR = DATASET_V1 / "corpus"
QUERIES_FILE = DATASET_V1 / "queries.jsonl"
QRELS_FILE = DATASET_V1 / "qrels.synthetic.jsonl"
ANSWERS_FILE = DATASET_V1 / "expected-answers.jsonl"
MANIFEST_FILE = DATASET_V1 / "corpus-manifest.json"
BASELINE_CONFIG_DEFAULT = BENCHMARK_ROOT / "configs" / "baseline.yaml"
CANDIDATE_CONFIG_DEFAULT = BENCHMARK_ROOT / "configs" / "candidate.yaml"
BUDGETS_CONFIG = BENCHMARK_ROOT / "configs" / "regression-budgets.yaml"
MODELS_LOCK = REPO_ROOT / "release" / "models.lock.json"

SEARCH_TOP_K = 10
RAG_TOP_K = 5
STRATA_ORDER = ("ua_to_ua", "en_to_en", "ua_to_en", "en_to_ua")
SEED = 42

logger = logging.getLogger("run_release_evaluation")


# ═════════════════════════════════════════════════════════════════════════════
#  Utility helpers
# ═════════════════════════════════════════════════════════════════════════════


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_jsonl(path: Path) -> str:
    items: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    text = json.dumps(items, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_jsonl(path: Path) -> list[dict]:
    items: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _get_git_info() -> tuple[str, bool]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=10,
        )
        commit = result.stdout.strip()
        result2 = subprocess.run(
            ["git", "status", "--porcelain"],  # noqa: S607
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=10,
        )
        dirty = bool(result2.stdout.strip())
        return commit, dirty
    except Exception:
        return "0" * 40, True


def _hardware_profile() -> dict[str, Any]:
    cpu = platform.processor() or platform.machine()
    cpuinfo = Path("/proc/cpuinfo")
    cpuinfo_text = ""
    if cpuinfo.exists():
        cpuinfo_text = cpuinfo.read_text(encoding="utf-8", errors="ignore")
        for line in cpuinfo_text.splitlines():
            if line.startswith("model name"):
                cpu = line.partition(":")[2].strip()
                break
    logical = os.cpu_count() or 0
    physical_ids: set[tuple[str, str]] = set()
    physical_id = core_id = ""
    for line in [*cpuinfo_text.splitlines(), ""]:
        if line.startswith("physical id"):
            physical_id = line.partition(":")[2].strip()
        elif line.startswith("core id"):
            core_id = line.partition(":")[2].strip()
        elif not line and (physical_id or core_id):
            physical_ids.add((physical_id, core_id))
            physical_id = core_id = ""
    mem_kib = 0
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        mem_kib = int(meminfo.read_text(encoding="utf-8").splitlines()[0].split()[1])
    return {
        "cpu": cpu,
        "logical_cores": logical,
        "physical_cores": len(physical_ids) or logical,
        "ram_gb": round(mem_kib / (1024**2), 1),
    }


def _dependency_lock_hash() -> str | None:
    candidates = [
        REPO_ROOT / "uv.lock",
        REPO_ROOT / "poetry.lock",
        REPO_ROOT / "Pipfile.lock",
    ]
    for c in candidates:
        if c.exists():
            return _sha256_file(c)
    return None


# ═════════════════════════════════════════════════════════════════════════════
#  Corpus materialisation
# ═════════════════════════════════════════════════════════════════════════════


def materialise_vault(target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    resource_dir = target / "03_Resources"
    resource_dir.mkdir(parents=True, exist_ok=True)
    for md_file in sorted(CORPUS_DIR.glob("*.md")):
        shutil.copy2(md_file, resource_dir / md_file.name)


# ═════════════════════════════════════════════════════════════════════════════
#  Vault sync (FTS-only / dense)
# ═════════════════════════════════════════════════════════════════════════════


def _db_path_for_vault(vault_dir: Path) -> Path:
    return vault_dir / ".power_search.db"


def _sync_vault(
    vault_dir: Path, sync_embeddings: bool, force_rebuild: bool = False
) -> None:
    db_path = _db_path_for_vault(vault_dir)
    os.environ["POWER_SEARCH_DB"] = str(db_path)

    conn = sqlite3.connect(str(db_path), timeout=30)

    from power_framework.core.db import _init_db

    _init_db(conn)

    from power_framework.core.searcher import _sync_vault_to_db

    _sync_vault_to_db(
        vault_dir, conn, sync_embeddings=sync_embeddings, force_rebuild=force_rebuild
    )
    conn.close()


# ═════════════════════════════════════════════════════════════════════════════
#  Search helpers
# ═════════════════════════════════════════════════════════════════════════════


def _search_and_collect(
    vault_dir: Path, query: str, mode: str, top_k: int = SEARCH_TOP_K
) -> list[dict]:
    from power_framework.core.searcher import search_vault

    results = search_vault(vault_dir, query, max_results=top_k, mode=mode)
    return [
        {
            "doc_id": Path(r.rel_path).name,
            "rel_path": r.rel_path,
            "score": r.score,
            "title": r.title,
            "description": r.description,
            "snippet": r.snippet,
        }
        for r in results
    ]


# ═════════════════════════════════════════════════════════════════════════════
#  Metrics
# ═════════════════════════════════════════════════════════════════════════════


def dcg_at_k(ranks: list[float], k: int) -> float:
    ranks = ranks[:k]
    if not ranks:
        return 0.0
    return sum(ranks[i] / math.log2(i + 2) for i in range(len(ranks)))


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    ranks = [1.0 if doc in relevant else 0.0 for doc in retrieved[:k]]
    ideal = sorted([1.0] * min(len(relevant), k), reverse=True)
    dcg = dcg_at_k(ranks, k)
    idcg = dcg_at_k(ideal, k)
    return dcg / idcg if idcg > 0 else 0.0


def mrr_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    for i, doc in enumerate(retrieved[:k]):
        if doc in relevant:
            return 1.0 / (i + 1)
    return 0.0


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not retrieved[:k]:
        return 0.0
    return len(set(retrieved[:k]) & relevant) / len(retrieved[:k])


def compute_query_metrics(
    retrieved: list[dict], relevant_docs: set[str]
) -> dict[str, float]:
    doc_ids = [r["doc_id"] for r in retrieved]
    return {
        "ndcg@10": ndcg_at_k(doc_ids, relevant_docs, 10),
        "mrr@10": mrr_at_k(doc_ids, relevant_docs, 10),
        "recall@5": recall_at_k(doc_ids, relevant_docs, 5),
        "precision@5": precision_at_k(doc_ids, relevant_docs, 5),
    }


# ═════════════════════════════════════════════════════════════════════════════
#  Paired comparison
# ═════════════════════════════════════════════════════════════════════════════


def paired_bootstrap_ci(
    baseline_scores: list[float],
    candidate_scores: list[float],
    n_resamples: int = 10000,
    ci: float = 0.95,
    seed: int = SEED,
) -> dict[str, Any]:
    rng = random.Random(seed)  # noqa: S311
    n = len(baseline_scores)
    deltas = [c - b for b, c in zip(baseline_scores, candidate_scores, strict=True)]
    mean_delta = sum(deltas) / n if n else 0.0

    if n == 0:
        return {
            "delta": 0.0,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
            "ci_level": ci,
            "n_resamples": n_resamples,
        }

    boot_deltas: list[float] = []
    for _ in range(n_resamples):
        sample = [rng.choice(deltas) for _ in range(n)]
        boot_deltas.append(sum(sample) / n)

    boot_deltas.sort()
    tail = int(n_resamples * (1 - ci) / 2)
    ci_lower = boot_deltas[tail]
    ci_upper = boot_deltas[n_resamples - tail - 1]

    return {
        "delta": mean_delta,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "ci_level": ci,
        "n_resamples": n_resamples,
    }


def exact_sign_test_pvalue(
    baseline_scores: list[float], candidate_scores: list[float]
) -> float:
    n = len(baseline_scores)
    if n == 0:
        return 1.0
    wins = sum(
        1 for b, c in zip(baseline_scores, candidate_scores, strict=True) if c > b
    )
    ties = sum(
        1 for b, c in zip(baseline_scores, candidate_scores, strict=True) if c == b
    )
    effective = n - ties
    if effective == 0:
        return 1.0
    tail = sum(math.comb(effective, k) for k in range(min(wins, effective - wins) + 1))
    return min(1.0, 2.0 * tail / (2**effective))


def compute_paired_stats(
    baseline_per_query: list[dict],
    candidate_per_query: list[dict],
    metric_key: str = "ndcg@10",
) -> dict[str, Any]:
    b_scores = [q[metric_key] for q in baseline_per_query]
    c_scores = [q[metric_key] for q in candidate_per_query]
    sample_size = len(b_scores)

    bootstrap = paired_bootstrap_ci(b_scores, c_scores)
    sign_p = exact_sign_test_pvalue(b_scores, c_scores)

    return {
        "metric": metric_key,
        "sample_size": sample_size,
        "baseline_mean": sum(b_scores) / sample_size if sample_size else 0.0,
        "candidate_mean": sum(c_scores) / sample_size if sample_size else 0.0,
        "delta": bootstrap["delta"],
        "ci_lower": bootstrap["ci_lower"],
        "ci_upper": bootstrap["ci_upper"],
        "ci_level": bootstrap["ci_level"],
        "bootstrap_resamples": bootstrap["n_resamples"],
        "sign_test_p_value": sign_p,
    }


# ═════════════════════════════════════════════════════════════════════════════
#  Deterministic extractive RAG
# ═════════════════════════════════════════════════════════════════════════════


def _find_atomic_fact_in_content(fact: str, content: str) -> bool:
    return fact.lower() in content.lower()


def run_extractive_rag(
    retrieved: list[dict],
    corpus_content: dict[str, str],
    expected_answer: dict,
    abstention_threshold: float = 0.0,
    distractor_doc_ids: set[str] | None = None,
) -> dict[str, Any]:
    no_answer = bool(expected_answer.get("no_answer", False))
    if not retrieved or float(retrieved[0]["score"]) < abstention_threshold:
        return {
            "answer": None,
            "citation": None,
            "abstained": True,
            "correctness": 1.0 if no_answer else 0.0,
            "groundedness": 1.0,
            "citation_accuracy": 1.0 if no_answer else 0.0,
            "distractor_sensitivity": None,
        }

    top_docs = retrieved[:RAG_TOP_K]
    retrieved_doc_ids = [r["doc_id"] for r in top_docs]
    cited_doc = retrieved_doc_ids[0]
    answer_text = "\n\n".join(corpus_content.get(did, "") for did in retrieved_doc_ids)

    if not answer_text:
        return {
            "answer": None,
            "citation": None,
            "abstained": True,
            "correctness": 1.0 if no_answer else 0.0,
            "groundedness": 0.0,
            "citation_accuracy": 0.0,
            "distractor_sensitivity": None,
        }

    if no_answer:
        return {
            "answer": answer_text,
            "citation": cited_doc,
            "abstained": False,
            "correctness": 0.0,
            "groundedness": 1.0,
            "citation_accuracy": 0.0,
            "distractor_sensitivity": None,
        }

    atomic_facts = expected_answer.get("atomic_facts", [])
    citation_ids = set(expected_answer.get("citation_document_ids", []))
    facts_found = [_find_atomic_fact_in_content(fact, answer_text) for fact in atomic_facts]

    all_facts_found = all(facts_found)
    correctness = 1.0 if all_facts_found else 0.0

    groundedness = sum(facts_found) / len(facts_found) if facts_found else 1.0
    cited_docs = set(retrieved_doc_ids) & citation_ids
    citation_accuracy = len(cited_docs) / len(citation_ids) if citation_ids else 1.0

    distractor_sensitivity = None
    if distractor_doc_ids:
        distractor_sensitivity = (
            0.0 if set(retrieved_doc_ids) <= distractor_doc_ids else 1.0
        )

    if not all_facts_found:
        return {
            "answer": None,
            "citation": None,
            "abstained": True,
            "correctness": correctness,
            "groundedness": groundedness,
            "citation_accuracy": citation_accuracy,
            "distractor_sensitivity": distractor_sensitivity,
        }

    return {
        "answer": answer_text,
        "citation": cited_doc,
        "abstained": False,
        "correctness": correctness,
        "groundedness": groundedness,
        "citation_accuracy": citation_accuracy,
        "distractor_sensitivity": distractor_sensitivity,
    }


def compute_rag_aggregates(rag_results: list[dict]) -> dict[str, Any]:
    n = len(rag_results)
    if n == 0:
        return {}
    answerable = [r for r in rag_results if r.get("retrieval_mode") != "no-answer"]
    no_answer_qs = [r for r in rag_results if r.get("retrieval_mode") == "no-answer"]

    correctness_vals = [
        r["correctness"] for r in answerable if r["correctness"] is not None
    ]
    groundedness_vals = [
        r["groundedness"] for r in answerable if r["groundedness"] is not None
    ]
    citation_vals = [
        r["citation_accuracy"] for r in answerable if r["citation_accuracy"] is not None
    ]
    abstentions = [r for r in answerable if r.get("abstained")]
    false_positives = [r for r in no_answer_qs if not r.get("abstained")]

    return {
        "answerable_count": len(answerable),
        "no_answer_count": len(no_answer_qs),
        "mean_correctness": (
            sum(correctness_vals) / len(correctness_vals) if correctness_vals else 0.0
        ),
        "mean_groundedness": (
            sum(groundedness_vals) / len(groundedness_vals)
            if groundedness_vals
            else 0.0
        ),
        "mean_citation_accuracy": (
            sum(citation_vals) / len(citation_vals) if citation_vals else 0.0
        ),
        "abstention_rate": len(abstentions) / len(answerable) if answerable else 0.0,
        "no_answer_false_positive_rate": (
            len(false_positives) / len(no_answer_qs) if no_answer_qs else 0.0
        ),
    }


# ═════════════════════════════════════════════════════════════════════════════
#  Main evaluation loop
# ═════════════════════════════════════════════════════════════════════════════


def run_evaluation(args: argparse.Namespace) -> dict[str, Any]:
    # ── Load configs ──────────────────────────────────────────────────────
    baseline_cfg = _load_yaml(Path(args.baseline_config))
    candidate_cfg = _load_yaml(Path(args.candidate_config))
    budgets = _load_yaml(BUDGETS_CONFIG)

    # ── Load dataset ──────────────────────────────────────────────────────
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    queries = _load_jsonl(QUERIES_FILE)
    qrels = _load_jsonl(QRELS_FILE)
    answers = _load_jsonl(ANSWERS_FILE)

    corpus_content: dict[str, str] = {
        f.name: f.read_text(encoding="utf-8") for f in sorted(CORPUS_DIR.glob("*.md"))
    }

    # Build qrels map: query_id -> set of relevant doc_ids (relevance >= 1)
    qrels_map: dict[str, set[str]] = {}
    for qr in qrels:
        qid = qr["query_id"]
        if qid not in qrels_map:
            qrels_map[qid] = set()
        qrels_map[qid].add(qr["document_id"])

    # Build distractor map: query_id -> set of distractor doc_ids
    distractor_map: dict[str, set[str]] = {}
    for qr in qrels:
        if qr.get("distractor", False):
            distractor_map.setdefault(qr["query_id"], set()).add(qr["document_id"])

    # Answer map
    answer_map: dict[str, dict] = {a["query_id"]: a for a in answers}

    # ── Materialise vault ─────────────────────────────────────────────────
    vault_dir = (
        Path(args.vault_dir)
        if args.vault_dir
        else Path(tempfile.mkdtemp(prefix="power31-vault-"))
    )

    if args.vault_dir:
        if vault_dir.exists():
            shutil.rmtree(vault_dir)
        vault_dir.mkdir(parents=True, exist_ok=True)

    materialise_vault(vault_dir)
    logger.info(
        "Vault materialised at %s with %d documents", vault_dir, len(corpus_content)
    )

    # ── Sync vault ────────────────────────────────────────────────────────
    db_path = _db_path_for_vault(vault_dir)
    os.environ["POWER_SEARCH_DB"] = str(db_path)

    # Baseline: FTS sync
    _sync_vault(vault_dir, sync_embeddings=False)
    logger.info("FTS sync complete (baseline)")

    # Candidate: dense sync
    try:
        _sync_vault(vault_dir, sync_embeddings=True, force_rebuild=True)
        logger.info("Dense sync complete (candidate)")
    except Exception:
        logger.exception("Dense sync failed; release evidence is invalid")
        raise

    # Ensure POWER_SEARCH_DB is set for search_vault calls
    os.environ["POWER_SEARCH_DB"] = str(db_path)
    os.environ["POWER_VAULT_DIR"] = str(vault_dir)

    # ── Run retrieval ─────────────────────────────────────────────────────
    baseline_mode = baseline_cfg.get("retrieval_mode", "fts")
    candidate_mode = candidate_cfg.get("retrieval_mode", "semantic")
    baseline_rag_threshold = float(baseline_cfg["rag_abstention_threshold"])
    candidate_rag_threshold = float(candidate_cfg["rag_abstention_threshold"])

    per_query_results: list[dict] = []
    baseline_per_query_metrics: list[dict] = []
    candidate_per_query_metrics: list[dict] = []
    rag_results_baseline: list[dict] = []
    rag_results_candidate: list[dict] = []

    latency_baseline: list[float] = []
    latency_candidate: list[float] = []

    for q in queries:
        qid = q["query_id"]
        stratum = q["stratum"]
        qclass = q["query_class"]
        is_no_answer = qclass == "no_answer"
        query_text = q["query"]

        relevant = qrels_map.get(qid, set())
        distractor = distractor_map.get(qid)
        expected_ans = answer_map.get(qid)

        # ── Baseline run ──────────────────────────────────────────────────
        t0 = time.monotonic()
        b_retrieved = _search_and_collect(vault_dir, query_text, baseline_mode)
        latency_baseline.append((time.monotonic() - t0) * 1000)

        b_metrics = (
            compute_query_metrics(b_retrieved, relevant) if not is_no_answer else {}
        )

        b_rag = run_extractive_rag(
            b_retrieved,
            corpus_content,
            expected_ans or {},
            baseline_rag_threshold,
            distractor_doc_ids=distractor,
        )
        b_rag["retrieval_mode"] = "no-answer" if is_no_answer else "answerable"

        # ── Candidate run ─────────────────────────────────────────────────
        t0 = time.monotonic()
        c_retrieved = _search_and_collect(vault_dir, query_text, candidate_mode)
        latency_candidate.append((time.monotonic() - t0) * 1000)

        c_metrics = (
            compute_query_metrics(c_retrieved, relevant) if not is_no_answer else {}
        )

        c_rag = run_extractive_rag(
            c_retrieved,
            corpus_content,
            expected_ans or {},
            candidate_rag_threshold,
            distractor_doc_ids=distractor,
        )
        c_rag["retrieval_mode"] = "no-answer" if is_no_answer else "answerable"

        # ── Collect ───────────────────────────────────────────────────────
        entry = {
            "query_id": qid,
            "stratum": stratum,
            "query_class": qclass,
            "query": query_text,
            "baseline": {
                "retrieved": b_retrieved,
                "metrics": b_metrics,
                "rag": b_rag,
            },
            "candidate": {
                "retrieved": c_retrieved,
                "metrics": c_metrics,
                "rag": c_rag,
            },
        }
        per_query_results.append(entry)

        if not is_no_answer:
            baseline_per_query_metrics.append(b_metrics)
            candidate_per_query_metrics.append(c_metrics)

        rag_results_baseline.append(b_rag)
        rag_results_candidate.append(c_rag)

    # ── Aggregate metrics per stratum ─────────────────────────────────────
    strata_agg: dict[str, dict[str, Any]] = {}
    for stratum in STRATA_ORDER:
        stratum_entries = [
            r
            for r in per_query_results
            if r["stratum"] == stratum and r["query_class"] != "no_answer"
        ]
        if not stratum_entries:
            continue
        base_metrics = [r["baseline"]["metrics"] for r in stratum_entries]
        cand_metrics = [r["candidate"]["metrics"] for r in stratum_entries]

        strata_agg[stratum] = {
            "count": len(stratum_entries),
            "baseline": _aggregate_metrics_list(base_metrics),
            "candidate": _aggregate_metrics_list(cand_metrics),
            "paired_stats": {
                metric_key: compute_paired_stats(base_metrics, cand_metrics, metric_key)
                for metric_key in ("ndcg@10", "mrr@10", "recall@5", "precision@5")
            },
        }

    # Overall aggregate
    overall_baseline_agg = _aggregate_metrics_list(baseline_per_query_metrics)
    overall_candidate_agg = _aggregate_metrics_list(candidate_per_query_metrics)

    # ── No-answer false-positive rate ─────────────────────────────────────
    no_answer_entries = [
        r for r in per_query_results if r["query_class"] == "no_answer"
    ]
    baseline_fp = sum(1 for r in no_answer_entries if not r["baseline"]["rag"].get("abstained"))
    candidate_fp = sum(1 for r in no_answer_entries if not r["candidate"]["rag"].get("abstained"))
    no_answer_count = len(no_answer_entries) or 1

    # ── Paired comparison ─────────────────────────────────────────────────
    paired_stats = {}
    for metric_key in ("ndcg@10", "mrr@10", "recall@5", "precision@5"):
        paired_stats[metric_key] = compute_paired_stats(
            baseline_per_query_metrics,
            candidate_per_query_metrics,
            metric_key,
        )

    # ── RAG aggregates ────────────────────────────────────────────────────
    rag_aggregates = {
        "baseline": compute_rag_aggregates(rag_results_baseline),
        "candidate": compute_rag_aggregates(rag_results_candidate),
    }

    # ── Latency ───────────────────────────────────────────────────────────
    def percentile(data: list[float], p: float) -> float:
        if not data:
            return 0.0
        s = sorted(data)
        idx = max(0, min(len(s) - 1, int(len(s) * p / 100)))
        return s[idx]

    latency_profile = {
        "baseline": {
            "p50_ms": percentile(latency_baseline, 50),
            "p95_ms": percentile(latency_baseline, 95),
        },
        "candidate": {
            "p50_ms": percentile(latency_candidate, 50),
            "p95_ms": percentile(latency_candidate, 95),
        },
    }

    # ── Peak RSS ──────────────────────────────────────────────────────────
    import resource as rs

    peak_rss = rs.getrusage(rs.RUSAGE_SELF).ru_maxrss

    # ── Assemble output ───────────────────────────────────────────────────
    timestamp_raw = (
        args.timestamp
        or os.environ.get("SOURCE_DATE_EPOCH")
        or datetime.now(timezone.utc).isoformat()
    )
    try:
        ts_epoch = int(timestamp_raw)
        ts_str = datetime.fromtimestamp(ts_epoch, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        ts_str = timestamp_raw

    git_commit, dirty_tree = _get_git_info()
    run_id = f"run-{hashlib.sha256(f'{git_commit}:{ts_str}'.encode()).hexdigest()[:8]}"

    output = {
        "run_id": run_id,
        "benchmark_version": baseline_cfg.get("benchmark_version", "3.1.0"),
        "timestamp": ts_str,
        "source_date": timestamp_raw,
        "git_commit": git_commit,
        "dirty_tree": dirty_tree,
        "config": {
            "baseline": {
                "file": str(baseline_cfg.get("evaluation_mode", "baseline")),
                "path": str(Path(args.baseline_config).resolve()),
                "sha256": _sha256_file(Path(args.baseline_config)),
            },
            "candidate": {
                "file": str(candidate_cfg.get("evaluation_mode", "candidate")),
                "path": str(Path(args.candidate_config).resolve()),
                "sha256": _sha256_file(Path(args.candidate_config)),
            },
        },
        "dataset": {
            "corpus_hash": manifest["corpus"]["hash_sha256"],
            "queries_hash": manifest["queries"]["hash_sha256"],
            "qrels_hash": manifest["qrels"]["hash_sha256"],
        },
        "dependency_lock_hash": _dependency_lock_hash(),
        "models_lock": {
            "hash": _sha256_file(MODELS_LOCK) if MODELS_LOCK.exists() else None,
            "revision": MODELS_LOCK.exists()
            and json.loads(MODELS_LOCK.read_text())
            .get("canonical_embedding", {})
            .get("revision"),
        },
        "python_version": sys.version,
        "platform": platform.platform(),
        "hardware": _hardware_profile(),
        "strata": {s: strata_agg.get(s, {"count": 0})["count"] for s in STRATA_ORDER},
        "total_queries": len(queries),
        "baseline_mode": baseline_mode,
        "candidate_mode": candidate_mode,
        "candidate_dense_available": True,
        "per_query_results": per_query_results,
        "aggregates": {
            "baseline": overall_baseline_agg,
            "candidate": overall_candidate_agg,
            "per_stratum": strata_agg,
            "no_answer_false_positive": {
                "baseline": baseline_fp,
                "candidate": candidate_fp,
                "total_no_answer": no_answer_count,
                "baseline_rate": baseline_fp / no_answer_count,
                "candidate_rate": candidate_fp / no_answer_count,
            },
        },
        "paired_stats": {
            "overall": paired_stats,
            "per_stratum": {
                stratum: strata_agg[stratum]["paired_stats"] for stratum in strata_agg
            },
        },
        "rag_metrics": rag_aggregates,
        "latency": latency_profile,
        "peak_rss_mb": round(peak_rss / 1024, 1),
        "regression_budgets": budgets,
        "scope_and_limitations": [
            "SYNTHETIC BENCHMARK — not human-annotated, not production evidence",
            "Relevance is rule-assigned by topic membership, not by human judges",
            "Results must not be cited as evidence of production retrieval quality",
            "Suitable for CI regression testing and release gates only",
        ],
    }

    return output  # noqa: RET504


def _aggregate_metrics_list(metrics_list: list[dict]) -> dict[str, float]:
    if not metrics_list:
        return {}
    keys = metrics_list[0].keys()
    result = {}
    for k in keys:
        vals = [m.get(k, 0.0) for m in metrics_list]
        result[k] = sum(vals) / len(vals)
    return result


# ═════════════════════════════════════════════════════════════════════════════
#  CLI
# ═════════════════════════════════════════════════════════════════════════════


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="POWER 3.1 Release-Evidence Evaluation Harness (E2/E3)",
    )
    parser.add_argument(
        "--baseline-config",
        default=str(BASELINE_CONFIG_DEFAULT),
        help="Path to baseline YAML config (default: benchmarks/power31/configs/baseline.yaml)",
    )
    parser.add_argument(
        "--candidate-config",
        default=str(CANDIDATE_CONFIG_DEFAULT),
        help="Path to candidate YAML config (default: benchmarks/power31/configs/candidate.yaml)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path for the evidence JSON (default: stdout)",
    )
    parser.add_argument(
        "--timestamp",
        default=None,
        help="ISO-8601 timestamp or Unix epoch integer for reproducible builds",
    )
    parser.add_argument(
        "--vault-dir",
        default=None,
        help="Path to materialise the vault (default: temp dir)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Deprecated compatibility option; use --vault-dir for a persistent vault",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    output = run_evaluation(args)

    output_json = json.dumps(output, indent=2, ensure_ascii=False, default=str)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_json, encoding="utf-8")
        logger.info("Evidence written to %s", out_path)
    else:
        print(output_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())

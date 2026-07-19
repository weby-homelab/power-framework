#!/usr/bin/env python3
"""P.O.W.E.R. v2.2.3 search quality benchmark with strict RAM (<14GB) guard.

Runs all 5 search modes over the frozen GT fixture and computes
MRR, Recall@5, nDCG@10 and UDCG@10. Runs semantic sync in background with a
hard RAM cap (kills the process if total system used memory exceeds limit).
"""

import json
import os
import sys
import time
import threading
import subprocess
from pathlib import Path

import psutil

from power_framework.core.searcher import search_vault
from power_framework.core.metrics.udcg import udcg

VAULT = Path("/root/gemma/brain").expanduser().resolve()
GT_PATH = Path("/root/gemma/projects/P.O.W.E.R/tests/fixtures/search_gt.json")
RAM_LIMIT_GB = 14.0
RESULTS_DIR = Path("/tmp/power_bench_223")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
RAM_LOG = RESULTS_DIR / "ram_monitor.log"

_stop = threading.Event()


def ram_guard():
    """Background thread: log used RAM, hard-kill process if over limit."""
    proc = psutil.Process(os.getpid())
    while not _stop.is_set():
        vm = psutil.virtual_memory()
        used_gb = vm.used / (1024**3)
        with open(RAM_LOG, "a") as f:
            f.write(f"{time.time():.1f} used={used_gb:.2f}GB limit={RAM_LIMIT_GB}GB\n")
        if used_gb > RAM_LIMIT_GB:
            print(f"\n!!! RAM LIMIT EXCEEDED: {used_gb:.2f}GB > {RAM_LIMIT_GB}GB -> KILLING")
            sys.stdout.flush()
            os._exit(137)
        time.sleep(1.0)


def sync_fts():
    print("[sync] FTS-only sync ...", flush=True)
    from power_framework.core.searcher import set_vault_dir, _sync_vault_to_db, _db_path

    set_vault_dir(VAULT)
    import sqlite3

    conn = sqlite3.connect(str(_db_path()), timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    from power_framework.core.searcher import _init_db

    _init_db(conn)
    _sync_vault_to_db(VAULT, conn, sync_embeddings=False)
    conn.close()
    print("[sync] FTS done", flush=True)


def run_query(query, mode, max_results=20):
    t0 = time.time()
    results = search_vault(VAULT, query, max_results=max_results, mode=mode)
    dt = time.time() - t0
    print(
        f"    [debug] q={query!r} mode={mode} -> {len(results)} results in {dt:.3f}s",
        file=sys.stderr,
    )
    return [r.rel_path for r in results], dt


def metrics(ranked, utilities, k=10):
    """Return (mrr, recall@5, ndcg@10, udcg@10)."""
    # MRR
    mrr = 0.0
    for i, p in enumerate(ranked, 1):
        if p in utilities and utilities[p] > 0:
            mrr = 1.0 / i
            break
    # Recall@5
    top5 = set(ranked[:5])
    rel = [p for p, u in utilities.items() if u > 0]
    recall5 = len(top5 & set(rel)) / len(rel) if rel else 0.0

    # graded gains
    def dcg(gains):
        return sum(g / (1 + i) for i, g in enumerate(gains))

    ideal = sorted(utilities.values(), reverse=True)[:k]
    ideal_dcg = dcg(ideal) if ideal else 1.0
    gains = [utilities.get(p, 0.0) for p in ranked[:k]]
    ndcg = dcg(gains) / ideal_dcg if ideal_dcg else 0.0
    # UDCG: utility-distraction aware
    try:
        udcg_val = udcg(gains)
    except Exception:
        udcg_val = float("nan")
    return mrr, recall5, ndcg, udcg_val


def main():
    gt = json.load(open(GT_PATH))
    queries = gt["queries"]

    # Start RAM guard
    g = threading.Thread(target=ram_guard, daemon=True)
    g.start()

    sync_fts()

    # Map mode -> gt group
    mode_to_group = {}
    all_q = []
    for group, items in queries.items():
        for it in items:
            all_q.append((group, it))
            mode_to_group[it["query"]] = it["mode"]

    # Also test every query in its own GT-declared mode (primary) and build a
    # per-mode aggregate. Additionally cross-run semantic/hybrid_reranked so
    # the embeddings get synced (triggers background semantic sync).
    per_mode = {}  # mode -> list of metric tuples

    report = {"modes": {}, "queries": [], "ram_log": str(RAM_LOG)}
    start_wall = time.time()

    # Ensure semantic sync happens at least once (warm embeddings table)
    for group, it in all_q:
        q = it["query"]
        mode = it["mode"]
        utils = it["utilities"]
        ranked, dt = run_query(q, mode)
        mrr, r5, ndcg, udcg = metrics(ranked, utils)
        per_mode.setdefault(mode, []).append((mrr, r5, ndcg, udcg))
        report["queries"].append(
            {
                "group": group,
                "query": q,
                "mode": mode,
                "mrr": round(mrr, 4),
                "recall5": round(r5, 4),
                "ndcg10": round(ndcg, 4),
                "udcg10": round(udcg, 4),
                "latency_s": round(dt, 3),
                "num_results": len(ranked),
                "top5": ranked[:5],
            }
        )
        print(
            f"[{mode:18}] {q[:40]:40} MRR={mrr:.3f} R@5={r5:.3f} nDCG={ndcg:.3f} UDCG={udcg:.3f} ({dt:.1f}s)",
            flush=True,
        )

    # Cross-matrix: run each query in ALL 5 modes to compare (semantic modes
    # reuse warmed embeddings).
    MODES = ["fts", "vector", "hybrid", "semantic", "hybrid_reranked"]
    matrix = {m: [] for m in MODES}
    for group, it in all_q:
        q = it["query"]
        utils = it["utilities"]
        for m in MODES:
            try:
                ranked, dt = run_query(q, m)
                mrr, r5, ndcg, udcg = metrics(ranked, utils)
                matrix[m].append((mrr, r5, ndcg, udcg))
                report.setdefault("matrix", {}).setdefault(q, {})[m] = {
                    "mrr": round(mrr, 4),
                    "recall5": round(r5, 4),
                    "ndcg10": round(ndcg, 4),
                    "udcg10": round(udcg, 4),
                    "latency_s": round(dt, 3),
                    "num_results": len(ranked),
                }
            except Exception as e:
                print(f"  !! mode {m} query {q}: {e}", flush=True)
                report.setdefault("matrix", {}).setdefault(q, {})[m] = {"error": str(e)}

    def agg(lst):
        if not lst:
            return None
        n = len(lst)
        return {
            "mrr": round(sum(x[0] for x in lst) / n, 4),
            "recall5": round(sum(x[1] for x in lst) / n, 4),
            "ndcg10": round(sum(x[2] for x in lst) / n, 4),
            "udcg10": round(sum(x[3] for x in lst) / n, 4),
        }

    report["modes"] = {m: agg(v) for m, v in per_mode.items()}
    report["matrix_agg"] = {m: agg(v) for m, v in matrix.items()}
    report["wall_time_s"] = round(time.time() - start_wall, 1)

    out = RESULTS_DIR / "benchmark_report.json"
    json.dump(report, open(out, "w"), indent=2, ensure_ascii=False)
    print("\n=== PER-MODE (GT-declared) ===", flush=True)
    for m, a in report["modes"].items():
        print(f"  {m:18} {a}", flush=True)
    print("\n=== MATRIX (all modes x all queries) ===", flush=True)
    for m, a in report["matrix_agg"].items():
        print(f"  {m:18} {a}", flush=True)
    print(f"\nWALL: {report['wall_time_s']}s  report: {out}", flush=True)
    _stop.set()


if __name__ == "__main__":
    try:
        main()
    finally:
        _stop.set()

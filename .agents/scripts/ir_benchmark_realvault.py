"""Real-vault IR benchmark on /root/gemma/brain (no gold labels).

Measures latency for all search modes and dumps top-1/top-5 per query for
qualitative analysis. No MRR/nDCG (no gold relevance), complementing
the synthetic-corpus benchmark which has gold labels.

Also enforces the Performance Plan §6 regression thresholds:
- semantic p95  < 1.0s  (after warm index)
- hybrid_reranked p95 < 3.0s
- fts p95 < 0.5s
The script exits non-zero if any threshold is breached.
"""

from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

from power_framework.core.searcher import search_vault

VAULT = Path("/root/gemma/brain")

# Regression thresholds (seconds). None disables the check for that mode.
THRESHOLDS = {
    "fts": 0.5,
    "vector": 1.0,
    "hybrid": 1.0,
    "semantic": 1.0,
    "hybrid_reranked": 3.0,
}

QUERIES = [
    "docker deployment container",
    "GPG signing git commit",
    "LLM inference speed benchmark GPU",
    "Proxmox LXC container network configuration",
    "FastAPI security authentication endpoint",
    "Pydantic validation schema metadata",
    "knowledge base second brain obsidian notes",
    "GitHub Actions CI CD workflow release",
    "VPN Tailscale network tunnel",
    "firewall security hardening audit",
    "MCP server agent tool integration",
    "backup archive storage Samba",
    "Power Safety Ukraine power outage",
    "embedding vector semantic search RAG",
    "docker container security deployment settings",
    "резервне копіювання бази даних postgres",
    "GPG signing git commit authentication",
    "налаштування VPN Tailscale мережевий тунель",
    "резервне копіювання бази даних",
    "firewall hardening security audit rules",
    "швидкість інференсу LLM на GPU бенчмарк",
    "MCP server agent tool integration protocol",
    "контейнер Proxmox LXC мережева конфігурація",
    "Obsidian second brain knowledge base notes",
    "автентифікація FastAPI безпека endpoint",
    "backup archive storage Samba share",
    "настройка фаервола аудит безопасности",
    "SSH port change configuration hardening",
    "синхронізація ролей бази знань автоматична",
    "semantic vector embedding search RAG",
    "відмова від галюцинацій пошук неіснуючих фактів",
    "оновлення зв'язків перейменування нотаток",
    "граф знань зв'язки проект база даних",
]


def _resolve_vault() -> Path:
    """Use the real vault if present; otherwise build a small synthetic corpus."""
    if VAULT.exists():
        return VAULT
    tmp = Path(tempfile.mkdtemp(prefix="power_bench_"))
    print(f"[bench] {VAULT} not found — generating synthetic corpus in {tmp}")
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "generate_corpus", Path(__file__).parent / "generate_corpus.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.generate_corpus(tmp, n_files=200)
    except Exception as e:
        print(f"[bench] corpus generation failed: {e}")
    return tmp


def main() -> None:
    vault = _resolve_vault()
    modes = sorted(THRESHOLDS.keys())

    # Warm up: build the semantic index once (background indexer won't run in CI).
    try:
        from power_framework.core.searcher import _sync_vault_to_db
        from power_framework.core.utils import get_cache_dir
        import sqlite3

        db_path = get_cache_dir() / "power_search.db"
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        from power_framework.core.searcher import _init_db

        _init_db(conn)
        print("Warming up: building full index (FTS + embeddings) ...")
        t0 = time.time()
        _sync_vault_to_db(vault, conn, sync_embeddings=True)
        print(f"Index build took {time.time() - t0:.2f}s")
        conn.close()
    except Exception as e:
        print(f"[bench] warmup index failed: {e}")

    lat: dict[str, list[float]] = {m: [] for m in modes}
    top1: dict[str, list[str | None]] = {m: [] for m in modes}
    top5: dict[str, list[list[str]]] = {m: [] for m in modes}

    for q in QUERIES:
        for m in modes:
            t0 = time.time()
            res = search_vault(vault, q, mode=m, max_results=20)
            dt = time.time() - t0
            lat[m].append(dt)
            top1[m].append(res[0].rel_path if res else None)
            top5[m].append([r.rel_path for r in res[:5]])

    summary = {}
    violations = []
    for m in modes:
        l = lat[m]
        p95 = sorted(l)[int(0.95 * (len(l) - 1))]
        summary[m] = {
            "AvgLatency": round(statistics.mean(l), 3),
            "MinLatency": round(min(l), 3),
            "P95Latency": round(p95, 3),
            "MaxLatency": round(max(l), 3),
        }
        thr = THRESHOLDS[m]
        if thr is not None and p95 > thr:
            violations.append(f"{m}: p95={p95:.3f}s > threshold {thr}s")

    out = {
        "vault": str(vault),
        "summary": summary,
        "top1": top1,
        "queries": QUERIES,
    }
    Path("/tmp/power_eval_realvault.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"summary": summary}, ensure_ascii=False, indent=2))

    print("\n=== Sample Top-1 (first 6 queries) ===")
    for i in range(6):
        print(f"Q: {QUERIES[i]}")
        for m in modes:
            print(f"   {m:16s} -> {top1[m][i]}")

    if violations:
        print("\n[FAIL] Performance regression thresholds breached:")
        for v in violations:
            print(f"  - {v}")
        raise SystemExit(1)
    print("\n[OK] All latency thresholds satisfied.")


if __name__ == "__main__":
    main()

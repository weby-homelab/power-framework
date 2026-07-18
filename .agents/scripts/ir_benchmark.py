"""Real IR benchmark for power-framework search on a generated 541+ vault.

Computes MRR, MAP@K, MAR@K, nDCG@K and latency for modes:
  fts, vector, hybrid, hybrid_reranked (Jina v2), semantic

Usage: python ir_benchmark.py
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from power_framework.core.searcher import search_vault

VAULT = Path("/tmp/power_bench_corpus")
MODES = ["fts", "vector", "hybrid", "hybrid_reranked", "semantic"]
K_VALUES = [1, 3, 5, 10]

# Query -> list of relevant rel_paths (target notes). Grades: 3=high, 2=rel, 1=partial
QUERIES: list[tuple[str, dict[str, int]]] = [
    (
        "docker deployment container",
        {"03_Resources/DockerDeployment.md": 3, "03_Resources/NalashtuvanniaDocker.md": 2},
    ),
    (
        "GPG signing git commit",
        {"02_Areas/Security/GpgSigning.md": 3, "02_Areas/Security/PidpysanniaGpg.md": 2},
    ),
    (
        "LLM inference speed benchmark GPU",
        {"03_Resources/LlmInferenceBenchmark.md": 3, "03_Resources/LlmBenchmarkUa.md": 2},
    ),
    (
        "Proxmox LXC container network configuration",
        {
            "02_Areas/Infrastructure/ProxmoxLxc.md": 3,
            "02_Areas/Infrastructure/ProxmoxLxcConfig.md": 2,
        },
    ),
    (
        "FastAPI security authentication endpoint",
        {"03_Resources/FastapiSecurity.md": 3, "03_Resources/FastapiAuthUa.md": 2},
    ),
    ("Pydantic validation schema metadata", {"03_Resources/PydanticValidation.md": 3}),
    (
        "knowledge base second brain obsidian notes",
        {"03_Resources/SecondBrain.md": 3, "03_Resources/DruhyiMozok.md": 2},
    ),
    ("GitHub Actions CI CD workflow release", {"01_Projects/CiCd/GitHubActions.md": 3}),
    (
        "VPN Tailscale network tunnel",
        {"02_Areas/Network/TailscaleVpn.md": 3, "02_Areas/Network/TailscaleSetup.md": 2},
    ),
    (
        "firewall security hardening audit",
        {
            "02_Areas/Security/FirewallHardening.md": 3,
            "02_Areas/Security/PravylaFirevolu.md": 2,
            "02_Areas/Security/FirewallAuditRu.md": 2,
        },
    ),
    (
        "MCP server agent tool integration",
        {"03_Resources/McpServer.md": 3, "03_Resources/IntegratsiiaMcp.md": 2},
    ),
    (
        "backup archive storage Samba",
        {"04_Archive/Storage/SambaBackup.md": 3, "04_Archive/Storage/SambaArhiv.md": 2},
    ),
    ("Power Safety Ukraine power outage", {"01_Projects/PowerSafetyUa.md": 3}),
    (
        "embedding vector semantic search RAG",
        {"03_Resources/EmbeddingRag.md": 3, "03_Resources/SemantuchnyiPoshyk.md": 2},
    ),
    # Cross-lingual
    (
        "docker container security deployment settings",
        {"03_Resources/NalashtuvanniaDocker.md": 3, "03_Resources/DockerDeployment.md": 2},
    ),
    (
        "резервне копіювання бази даних postgres",
        {"03_Resources/PostgresBackup.md": 3, "03_Resources/PostgresBackupUa.md": 3},
    ),
    (
        "GPG signing git commit authentication",
        {"02_Areas/Security/PidpysanniaGpg.md": 3, "02_Areas/Security/GpgSigning.md": 2},
    ),
    (
        "налаштування VPN Tailscale мережевий тунель",
        {"02_Areas/Network/TailscaleSetup.md": 3, "02_Areas/Network/TailscaleVpn.md": 2},
    ),
    (
        "резервне копіювання бази даних",
        {"03_Resources/PostgresBackupUa.md": 3, "03_Resources/PostgresBackup.md": 3},
    ),
    (
        "firewall hardening security audit rules",
        {
            "02_Areas/Security/PravylaFirevolu.md": 3,
            "02_Areas/Security/FirewallHardening.md": 2,
            "02_Areas/Security/FirewallAuditRu.md": 2,
        },
    ),
    (
        "швидкість інференсу LLM на GPU бенчмарк",
        {"03_Resources/LlmBenchmarkUa.md": 3, "03_Resources/LlmInferenceBenchmark.md": 2},
    ),
    (
        "MCP server agent tool integration protocol",
        {"03_Resources/IntegratsiiaMcp.md": 3, "03_Resources/McpServer.md": 2},
    ),
    (
        "контейнер Proxmox LXC мережева конфігурація",
        {
            "02_Areas/Infrastructure/ProxmoxLxcConfig.md": 3,
            "02_Areas/Infrastructure/ProxmoxLxc.md": 2,
        },
    ),
    (
        "Obsidian second brain knowledge base notes",
        {"03_Resources/DruhyiMozok.md": 3, "03_Resources/SecondBrain.md": 2},
    ),
    (
        "автентифікація FastAPI безпека endpoint",
        {"03_Resources/FastapiAuthUa.md": 3, "03_Resources/FastapiSecurity.md": 2},
    ),
    (
        "backup archive storage Samba share",
        {"04_Archive/Storage/SambaArhiv.md": 3, "04_Archive/Storage/SambaBackup.md": 2},
    ),
    (
        "настройка фаервола аудит безопасности",
        {
            "02_Areas/Security/FirewallAuditRu.md": 3,
            "02_Areas/Security/FirewallHardening.md": 2,
            "02_Areas/Security/PravylaFirevolu.md": 2,
        },
    ),
    ("SSH port change configuration hardening", {"02_Areas/Security/ZminaPortuSsh.md": 3}),
    ("синхронізація ролей бази знань автоматична", {"03_Resources/KnowledgeBaseSync.md": 3}),
    (
        "semantic vector embedding search RAG",
        {"03_Resources/SemantuchnyiPoshyk.md": 3, "03_Resources/EmbeddingRag.md": 2},
    ),
    ("відмова від галюцинацій пошук неіснуючих фактів", {"03_Resources/AbstentionNotes.md": 3}),
    ("оновлення зв'язків перейменування нотаток", {"03_Resources/OnovlenniaZviazkiv.md": 3}),
    ("граф знань зв'язки проект база даних", {"03_Resources/KnowledgeGraph.md": 3}),
]

CL_QUERIES = set(range(14, 32))  # indices of cross-lingual queries (0-based)


def dcg(grades_at_positions: list[float]) -> float:
    """grades_at_positions: relevance grade (0..3) of doc at rank i (1-based)."""
    return sum(g / (1.0 + i) for i, g in enumerate(grades_at_positions))


def evaluate(query: str, relevants: dict[str, int], results: list, k: int) -> dict:
    """Return per-query metrics at rank k."""
    grades = []
    hit_ranks = []
    for i, r in enumerate(results[:k], 1):
        g = float(relevants.get(r.rel_path, 0))
        grades.append(g)
        if g > 0:
            if g >= 2:  # "relevant" or "highly relevant" counts for MRR/hit
                hit_ranks.append(i)
    # MRR: first hit of grade>=2
    mrr = (1.0 / hit_ranks[0]) if hit_ranks else 0.0
    # MAP proxy: precision at k (fraction of top-k that are relevant grade>=1)
    rel_in_k = sum(1 for g in grades if g > 0)
    precision = rel_in_k / k if k else 0.0
    # MAR: fraction of ALL relevant docs found in top-k
    total_rel = len([v for v in relevants.values() if v >= 1])
    found_rel = sum(1 for r in results[:k] if relevants.get(r.rel_path, 0) >= 1)
    mar = found_rel / total_rel if total_rel else 0.0
    # nDCG
    ideal = sorted([float(v) for v in relevants.values() if v >= 1], reverse=True)[:k]
    idcg = dcg(ideal) if ideal else 0.0
    ndcg = dcg(grades) / idcg if idcg > 0 else 0.0
    return {
        "mrr": mrr,
        "precision": precision,
        "mar": mar,
        "ndcg": ndcg,
        "found_first_relevant_rank": hit_ranks[0] if hit_ranks else None,
    }


def main() -> None:
    # Warm up: build the DB/cache once
    print("Warming up index/cache on vault:", VAULT)
    t0 = time.time()
    search_vault(VAULT, "warmup docker container", mode="hybrid_reranked", max_results=5)
    print(f"Warmup took {time.time() - t0:.2f}s")

    aggregate: dict[str, dict] = {
        m: {
            "mrr": [],
            "map3": [],
            "map5": [],
            "mar5": [],
            "mar10": [],
            "ndcg5": [],
            "ndcg10": [],
            "lat": [],
        }
        for m in MODES
    }
    per_query: list[dict] = []

    for qi, (q, rel) in enumerate(QUERIES):
        is_cl = qi in CL_QUERIES
        row = {"query": q, "cl": is_cl, "rel": rel}
        for mode in MODES:
            t0 = time.time()
            res = search_vault(VAULT, q, mode=mode, max_results=20)
            dt = time.time() - t0
            e1 = evaluate(q, rel, res, 1)
            e3 = evaluate(q, rel, res, 3)
            e5 = evaluate(q, rel, res, 5)
            e10 = evaluate(q, rel, res, 10)
            agg = aggregate[mode]
            agg["mrr"].append(e1["mrr"])
            agg["map3"].append(e3["precision"])
            agg["map5"].append(e5["precision"])
            agg["mar5"].append(e5["mar"])
            agg["mar10"].append(e10["mar"])
            agg["ndcg5"].append(e5["ndcg"])
            agg["ndcg10"].append(e10["ndcg"])
            agg["lat"].append(dt)
            row[mode] = {
                "mrr": round(e1["mrr"], 3),
                "map5": round(e5["precision"], 3),
                "mar5": round(e5["mar"], 3),
                "ndcg5": round(e5["ndcg"], 3),
                "lat": round(dt, 3),
                "top1": res[0].rel_path if res else None,
            }
        per_query.append(row)

    # Aggregate summaries
    summary = {}
    for m in MODES:
        a = aggregate[m]
        summary[m] = {
            "MRR": round(statistics.mean(a["mrr"]), 3),
            "MAP@3": round(statistics.mean(a["map3"]), 3),
            "MAP@5": round(statistics.mean(a["map5"]), 3),
            "MAR@5": round(statistics.mean(a["mar5"]), 3),
            "MAR@10": round(statistics.mean(a["mar10"]), 3),
            "MnDCG@5": round(statistics.mean(a["ndcg5"]), 3),
            "MnDCG@10": round(statistics.mean(a["ndcg10"]), 3),
            "AvgLatency": round(statistics.mean(a["lat"]), 3),
            "P95Latency": round(sorted(a["lat"])[int(0.95 * (len(a["lat"]) - 1))], 3),
        }
    # Cross-lingual only
    cl_summary = {}
    for m in MODES:
        a = aggregate[m]
        idxs = [i for i in range(len(QUERIES)) if i in CL_QUERIES]
        cl_summary[m] = {
            "MRR": round(statistics.mean([a["mrr"][i] for i in idxs]), 3),
            "MAR@5": round(statistics.mean([a["mar5"][i] for i in idxs]), 3),
            "MnDCG@5": round(statistics.mean([a["ndcg5"][i] for i in idxs]), 3),
        }

    out = {"summary": summary, "cl_summary": cl_summary, "per_query": per_query}
    (VAULT.parent / "power_eval_cl_results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"summary": summary, "cl_summary": cl_summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

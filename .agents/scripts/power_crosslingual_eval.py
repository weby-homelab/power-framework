#!/usr/bin/env python3
"""
P.O.W.E.R. 2.0.3 — Cross-Lingual Search Quality Evaluation
Tests: UA→UA, EN→UA, UA→EN, Mixed→Mixed scenarios
Metrics: MRR, MAP@K, MAR@K, nDCG@K, Latency
"""
import subprocess
import json
import time
import sys
import math
from pathlib import Path

VAULT_PATH = "/root/geminicli/brain"
MODES = ["fts", "vector", "hybrid", "semantic", "hybrid_reranked"]
K_VALUES = [1, 3, 5, 10]

# ─── Cross-lingual Test Dataset ──────────────────────────────────────────────
# scenario: "ua_ua" | "en_ua" | "ua_en" | "mixed"
# relevant: list of path substrings to match
# grades: {path_substr: grade} — 3=highly relevant, 2=relevant, 1=partial
TEST_CASES = [
    # ── UA query → UA document ────────────────────────────────────────────────
    {
        "id": "CL-01", "scenario": "ua_ua",
        "query": "докер розгортання контейнер",
        "relevant": ["Docker-Mailserver-GUI", "Deployment", "Power-Safety-UA", "docker"],
        "grades": {"Docker-Mailserver-GUI": 3, "Deployment": 2, "Power-Safety-UA": 2},
        "description": "UA→UA: докер розгортання",
    },
    {
        "id": "CL-02", "scenario": "ua_ua",
        "query": "безпека файрвол аудит захист",
        "relevant": ["Global_Hardening", "MASTER-LESSONS-LEARNED", "security", "firewall"],
        "grades": {"Global_Hardening": 3, "MASTER-LESSONS-LEARNED": 2},
        "description": "UA→UA: безпека файрвол",
    },
    {
        "id": "CL-03", "scenario": "ua_ua",
        "query": "база знань нотатки другий мозок",
        "relevant": ["POWER_Framework", "AI-HomeLab", "brain", "knowledge"],
        "grades": {"POWER_Framework": 3, "AI-HomeLab": 2},
        "description": "UA→UA: база знань PKM",
    },
    {
        "id": "CL-04", "scenario": "ua_ua",
        "query": "резервне копіювання зберігання архів",
        "relevant": ["Successor-Hub", "backup", "archive", "samba"],
        "grades": {"Successor-Hub": 3, "archive": 1},
        "description": "UA→UA: резервне копіювання",
    },
    {
        "id": "CL-05", "scenario": "ua_ua",
        "query": "мережа VPN тунель налаштування",
        "relevant": ["Successor-Hub", "network", "tailscale", "VPN"],
        "grades": {"Successor-Hub": 3, "network": 2},
        "description": "UA→UA: мережа VPN",
    },
    {
        "id": "CL-06", "scenario": "ua_ua",
        "query": "штучний інтелект агент інструменти інтеграція",
        "relevant": ["POWER_Framework", "AI-HomeLab", "MCP", "agent"],
        "grades": {"POWER_Framework": 3, "AI-HomeLab": 2},
        "description": "UA→UA: AI агент MCP",
    },
    {
        "id": "CL-07", "scenario": "ua_ua",
        "query": "реліз версія деплой GitHub",
        "relevant": ["MASTER-LESSONS-LEARNED", "Power_Framework_v1.8.0_Deployment", "release"],
        "grades": {"MASTER-LESSONS-LEARNED": 3, "Power_Framework_v1.8.0_Deployment": 2},
        "description": "UA→UA: реліз GitHub",
    },
    {
        "id": "CL-08", "scenario": "ua_ua",
        "query": "підпис коміт GPG ключ",
        "relevant": ["MASTER-LESSONS-LEARNED", "Successor-Hub", "security"],
        "grades": {"MASTER-LESSONS-LEARNED": 3, "Successor-Hub": 2},
        "description": "UA→UA: GPG підпис коміту",
    },
    # ── EN query → UA document ────────────────────────────────────────────────
    {
        "id": "CL-09", "scenario": "en_ua",
        "query": "docker container deployment",
        "relevant": ["Docker-Mailserver-GUI", "Deployment", "Power-Safety-UA"],
        "grades": {"Docker-Mailserver-GUI": 3, "Deployment": 2},
        "description": "EN→UA: docker deployment (UA docs)",
    },
    {
        "id": "CL-10", "scenario": "en_ua",
        "query": "security firewall hardening audit",
        "relevant": ["Global_Hardening", "MASTER-LESSONS-LEARNED"],
        "grades": {"Global_Hardening": 3, "MASTER-LESSONS-LEARNED": 2},
        "description": "EN→UA: security hardening (UA docs)",
    },
    {
        "id": "CL-11", "scenario": "en_ua",
        "query": "backup storage archive files",
        "relevant": ["Successor-Hub", "archive", "backup"],
        "grades": {"Successor-Hub": 3, "archive": 1},
        "description": "EN→UA: backup storage (UA docs)",
    },
    {
        "id": "CL-12", "scenario": "en_ua",
        "query": "release version deployment GitHub Actions",
        "relevant": ["MASTER-LESSONS-LEARNED", "Power_Framework_v1.8.0_Deployment"],
        "grades": {"MASTER-LESSONS-LEARNED": 3, "Power_Framework_v1.8.0_Deployment": 2},
        "description": "EN→UA: release deployment (UA docs)",
    },
    # ── UA query → EN document ────────────────────────────────────────────────
    {
        "id": "CL-13", "scenario": "ua_en",
        "query": "валідація схема метадані нотатки",
        "relevant": ["POWER_Framework", "MASTER-LESSONS-LEARNED"],
        "grades": {"POWER_Framework": 3, "MASTER-LESSONS-LEARNED": 2},
        "description": "UA→EN: валідація схема (EN docs)",
    },
    {
        "id": "CL-14", "scenario": "ua_en",
        "query": "семантичний пошук векторні ембедінги",
        "relevant": ["POWER_Framework", "AI-HomeLab"],
        "grades": {"POWER_Framework": 3, "AI-HomeLab": 2},
        "description": "UA→EN: семантичний пошук (EN docs)",
    },
    {
        "id": "CL-15", "scenario": "ua_en",
        "query": "машинне навчання локальна модель швидкість",
        "relevant": ["MASTER-LESSONS-LEARNED", "AI-HomeLab"],
        "grades": {"MASTER-LESSONS-LEARNED": 3, "AI-HomeLab": 2},
        "description": "UA→EN: ML inference (EN docs)",
    },
    {
        "id": "CL-16", "scenario": "ua_en",
        "query": "SSH порт зміна конфігурація безпека",
        "relevant": ["SSH Port Changer", "Global_Hardening", "MASTER-LESSONS-LEARNED"],
        "grades": {"SSH Port Changer": 3, "Global_Hardening": 2},
        "description": "UA→EN: SSH конфігурація (EN docs)",
    },
    # ── Mixed language queries ─────────────────────────────────────────────────
    {
        "id": "CL-17", "scenario": "mixed",
        "query": "docker безпека container захист",
        "relevant": ["Docker-Mailserver-GUI", "Global_Hardening", "MASTER-LESSONS-LEARNED"],
        "grades": {"Docker-Mailserver-GUI": 3, "Global_Hardening": 2, "MASTER-LESSONS-LEARNED": 2},
        "description": "MIXED: docker+безпека (EN+UA mix)",
    },
    {
        "id": "CL-18", "scenario": "mixed",
        "query": "GitHub Actions реліз CI/CD деплой",
        "relevant": ["MASTER-LESSONS-LEARNED", "Power_Framework_v1.8.0_Deployment"],
        "grades": {"MASTER-LESSONS-LEARNED": 3, "Power_Framework_v1.8.0_Deployment": 2},
        "description": "MIXED: GitHub Actions+реліз",
    },
    {
        "id": "CL-19", "scenario": "mixed",
        "query": "MCP агент server integration інструменти",
        "relevant": ["POWER_Framework", "AI-HomeLab"],
        "grades": {"POWER_Framework": 3, "AI-HomeLab": 2},
        "description": "MIXED: MCP агент+integration",
    },
    {
        "id": "CL-20", "scenario": "mixed",
        "query": "Proxmox LXC контейнер мережа network",
        "relevant": ["Successor-Hub", "MASTER-LESSONS-LEARNED"],
        "grades": {"Successor-Hub": 3, "MASTER-LESSONS-LEARNED": 2},
        "description": "MIXED: Proxmox+мережа",
    },
]


def run_search(vault_path, query, mode, max_results=10):
    cmd = ["power", "search", vault_path, query, "--mode", mode, "--max-results", str(max_results)]
    try:
        t0 = time.perf_counter()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        elapsed = time.perf_counter() - t0
        lines = result.stdout.strip().split('\n') if result.stdout else []
        results = []
        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith("Path:"):
                path = line_stripped.split("Path:", 1)[1].strip()
                results.append({"path": path, "raw": line})
        return results, elapsed
    except subprocess.TimeoutExpired:
        return [], 999.0
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return [], 999.0


def is_relevant(path, relevant):
    path_lower = path.lower()
    return any(kw.lower() in path_lower for kw in relevant)


def get_grade(path, grades):
    path_lower = path.lower()
    return max((g for kw, g in grades.items() if kw.lower() in path_lower), default=0)


def precision_at_k(results, relevant, k):
    top_k = results[:k]
    return sum(1 for r in top_k if is_relevant(r["path"], relevant)) / k if k > 0 else 0.0


def recall_at_k(results, relevant, k):
    top_k = results[:k]
    hits = sum(1 for r in top_k if is_relevant(r["path"], relevant))
    return hits / len(relevant) if relevant else 0.0


def reciprocal_rank(results, relevant):
    for i, r in enumerate(results):
        if is_relevant(r["path"], relevant):
            return 1.0 / (i + 1)
    return 0.0


def dcg_at_k(results, grades, k):
    return sum(get_grade(r["path"], grades) / math.log2(i + 2) for i, r in enumerate(results[:k]))


def idcg_at_k(grades, k):
    return sum(g / math.log2(i + 2) for i, g in enumerate(sorted(grades.values(), reverse=True)[:k]))


def ndcg_at_k(results, grades, k):
    dcg = dcg_at_k(results, grades, k)
    idcg = idcg_at_k(grades, k)
    return dcg / idcg if idcg > 0 else 0.0


def evaluate_mode(mode, test_cases):
    print(f"\n{'='*60}\n  Evaluating mode: {mode.upper()}\n{'='*60}")
    results_by_tc = {}
    latencies = []

    for tc in test_cases:
        print(f"  [{tc['id']}][{tc['scenario']}] {tc['description'][:45]}...", end=" ", flush=True)
        results, latency = run_search(VAULT_PATH, tc["query"], mode)
        latencies.append(latency)

        metrics = {}
        for k in K_VALUES:
            metrics[f"P@{k}"]    = precision_at_k(results, tc["relevant"], k)
            metrics[f"R@{k}"]    = recall_at_k(results, tc["relevant"], k)
            metrics[f"nDCG@{k}"] = ndcg_at_k(results, tc["grades"], k)
        metrics["RR"]      = reciprocal_rank(results, tc["relevant"])
        metrics["latency"] = latency
        metrics["results"] = [r["path"] for r in results[:5]]
        results_by_tc[tc["id"]] = metrics

        hit = "✓" if metrics["R@5"] > 0 else "✗"
        print(f"{hit} R@5={metrics['R@5']:.2f} MRR={metrics['RR']:.2f} nDCG@5={metrics['nDCG@5']:.2f} ({latency:.2f}s)")

    agg = {}
    for k in K_VALUES:
        agg[f"MAP@{k}"]  = sum(m[f"P@{k}"]    for m in results_by_tc.values()) / len(test_cases)
        agg[f"MAR@{k}"]  = sum(m[f"R@{k}"]    for m in results_by_tc.values()) / len(test_cases)
        agg[f"MnDCG@{k}"]= sum(m[f"nDCG@{k}"] for m in results_by_tc.values()) / len(test_cases)
    agg["MRR"]          = sum(m["RR"]      for m in results_by_tc.values()) / len(test_cases)
    agg["avg_latency"]  = sum(latencies) / len(latencies)
    agg["p95_latency"]  = sorted(latencies)[int(len(latencies) * 0.95)]

    return {"per_tc": results_by_tc, "aggregate": agg}


def scenario_aggregate(all_results, scenario_ids, mode):
    """Aggregate metrics for a specific scenario subset."""
    tcs = [tc for tc in TEST_CASES if tc["id"] in scenario_ids]
    if not tcs:
        return {}
    per_tc = all_results[mode]["per_tc"]
    agg = {}
    for k in [3, 5, 10]:
        agg[f"MAR@{k}"] = sum(per_tc[tc["id"]][f"R@{k}"] for tc in tcs) / len(tcs)
        agg[f"MnDCG@{k}"] = sum(per_tc[tc["id"]][f"nDCG@{k}"] for tc in tcs) / len(tcs)
    agg["MRR"] = sum(per_tc[tc["id"]]["RR"] for tc in tcs) / len(tcs)
    return agg


def main():
    print("=" * 60)
    print("  P.O.W.E.R. 2.0.3 — Cross-Lingual Search Evaluation")
    print(f"  Vault: {VAULT_PATH}")
    print(f"  Test cases: {len(TEST_CASES)} (UA→UA, EN→UA, UA→EN, Mixed)")
    print(f"  Modes: {MODES}")
    print("=" * 60)

    vault = Path(VAULT_PATH)
    md_files = list(vault.rglob("*.md"))
    print(f"  Total .md files: {len(md_files)}")

    scenarios = {
        "ua_ua": [tc["id"] for tc in TEST_CASES if tc["scenario"] == "ua_ua"],
        "en_ua": [tc["id"] for tc in TEST_CASES if tc["scenario"] == "en_ua"],
        "ua_en": [tc["id"] for tc in TEST_CASES if tc["scenario"] == "ua_en"],
        "mixed": [tc["id"] for tc in TEST_CASES if tc["scenario"] == "mixed"],
    }
    print(f"  Scenarios: UA→UA={len(scenarios['ua_ua'])}, EN→UA={len(scenarios['en_ua'])}, UA→EN={len(scenarios['ua_en'])}, Mixed={len(scenarios['mixed'])}")

    all_results = {}
    for mode in MODES:
        all_results[mode] = evaluate_mode(mode, TEST_CASES)

    # ── Overall Summary ────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  OVERALL AGGREGATE METRICS (all 20 queries)")
    print("=" * 80)
    header = f"{'Metric':<22}" + "".join(f"{m.upper():>16}" for m in MODES)
    print(header)
    print("-" * 80)
    for label, key in [
        ("MRR",          "MRR"),
        ("MAP@5",        "MAP@5"),
        ("MAR@5",        "MAR@5"),
        ("MAR@10",       "MAR@10"),
        ("MnDCG@5",      "MnDCG@5"),
        ("MnDCG@10",     "MnDCG@10"),
        ("Avg Latency(s)","avg_latency"),
        ("P95 Latency(s)","p95_latency"),
    ]:
        row = f"{label:<22}" + "".join(f"{all_results[m]['aggregate'].get(key,0):>16.3f}" for m in MODES)
        print(row)

    # ── Per-Scenario MAR@5 ────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  MAR@5 BY SCENARIO (cross-lingual breakdown)")
    print("=" * 80)
    scenario_labels = {
        "ua_ua": "UA query → UA doc",
        "en_ua": "EN query → UA doc",
        "ua_en": "UA query → EN doc",
        "mixed": "Mixed query",
    }
    header2 = f"{'Scenario':<25}" + "".join(f"{m.upper():>16}" for m in MODES)
    print(header2)
    print("-" * 80)
    for sc_key, sc_label in scenario_labels.items():
        sc_ids = scenarios[sc_key]
        row = f"{sc_label:<25}"
        for mode in MODES:
            agg = scenario_aggregate(all_results, sc_ids, mode)
            row += f"{agg.get('MAR@5', 0):>16.3f}"
        print(row)

    # ── Per-TC Table ─────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  PER-QUERY R@5 DETAIL")
    print("=" * 80)
    header3 = f"{'ID':<8}{'Scen':<8}{'Description':<37}" + "".join(f"{m.upper():>10}" for m in MODES)
    print(header3)
    print("-" * 80)
    for tc in TEST_CASES:
        row = f"{tc['id']:<8}{tc['scenario']:<8}{tc['description'][:36]:<37}"
        for mode in MODES:
            val = all_results[mode]["per_tc"][tc["id"]]["R@5"]
            row += f"{val:>10.2f}"
        print(row)

    # ── Save JSON ─────────────────────────────────────────────────────────────
    out = "/tmp/power_crosslingual_eval.json"
    with open(out, "w") as f:
        json.dump({
            "vault_files": len(md_files),
            "test_cases": len(TEST_CASES),
            "scenarios": {k: len(v) for k, v in scenarios.items()},
            "modes": MODES,
            "results": {
                mode: {
                    "aggregate": data["aggregate"],
                    "per_tc": {
                        tc_id: {k: v for k, v in m.items() if k != "results"}
                        for tc_id, m in data["per_tc"].items()
                    },
                    "by_scenario": {
                        sc_key: scenario_aggregate(all_results, sc_ids, mode)
                        for sc_key, sc_ids in scenarios.items()
                    }
                }
                for mode, data in all_results.items()
            }
        }, f, indent=2)
    print(f"\n  ✓ JSON saved: {out}")
    print("  Cross-lingual evaluation complete.")
    return all_results


if __name__ == "__main__":
    main()

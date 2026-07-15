#!/usr/bin/env python3
"""
P.O.W.E.R. 2.0.3 Search Quality Evaluation Script
Measures: Recall@K, MRR@K, nDCG@K, Precision@K across all 3 search modes
"""
import subprocess
import json
import time
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import math

VAULT_PATH = "/root/geminicli/brain"

# ─── Test Dataset ────────────────────────────────────────────────────────────
# Format: (query, [relevant_file_substrings], relevance_grades {path_substr: grade})
# Grade: 3=highly relevant, 2=relevant, 1=partially relevant
TEST_CASES = [
    {
        "id": "TC-01",
        "query": "docker deployment container",
        "relevant": [
            "Docker-Mailserver-GUI",
            "Power-Safety-UA",
            "POWER_Framework",
            "docker",
        ],
        "grades": {
            "Docker-Mailserver-GUI": 3,
            "Power-Safety-UA": 2,
            "POWER_Framework": 2,
            "docker": 2,
        },
        "description": "Docker & container management"
    },
    {
        "id": "TC-02",
        "query": "GPG signing git commit",
        "relevant": [
            "MASTER-LESSONS-LEARNED",
            "Successor-Hub",
            "security",
            "git",
        ],
        "grades": {
            "MASTER-LESSONS-LEARNED": 3,
            "Successor-Hub": 2,
            "security": 2,
        },
        "description": "GPG & Git security"
    },
    {
        "id": "TC-03",
        "query": "LLM inference speed benchmark GPU",
        "relevant": [
            "MASTER-LESSONS-LEARNED",
            "AI-HomeLab",
            "llm",
            "inference",
        ],
        "grades": {
            "MASTER-LESSONS-LEARNED": 3,
            "AI-HomeLab": 2,
        },
        "description": "LLM benchmarking"
    },
    {
        "id": "TC-04",
        "query": "Proxmox LXC container network configuration",
        "relevant": [
            "Successor-Hub",
            "MASTER-LESSONS-LEARNED",
            "network",
            "proxmox",
        ],
        "grades": {
            "Successor-Hub": 3,
            "MASTER-LESSONS-LEARNED": 2,
        },
        "description": "Proxmox/LXC infrastructure"
    },
    {
        "id": "TC-05",
        "query": "FastAPI security authentication endpoint",
        "relevant": [
            "MASTER-LESSONS-LEARNED",
            "security",
            "fastapi",
            "API",
        ],
        "grades": {
            "MASTER-LESSONS-LEARNED": 3,
            "security": 2,
        },
        "description": "FastAPI security"
    },
    {
        "id": "TC-06",
        "query": "Pydantic validation schema metadata",
        "relevant": [
            "POWER_Framework",
            "MASTER-LESSONS-LEARNED",
            "pydantic",
        ],
        "grades": {
            "POWER_Framework": 3,
            "MASTER-LESSONS-LEARNED": 2,
        },
        "description": "Pydantic/schema validation"
    },
    {
        "id": "TC-07",
        "query": "knowledge base second brain obsidian notes",
        "relevant": [
            "POWER_Framework",
            "AI-HomeLab",
            "brain",
            "knowledge",
        ],
        "grades": {
            "POWER_Framework": 3,
            "AI-HomeLab": 2,
        },
        "description": "Second Brain / PKM"
    },
    {
        "id": "TC-08",
        "query": "GitHub Actions CI CD workflow release",
        "relevant": [
            "MASTER-LESSONS-LEARNED",
            "Power_Framework_v1.8.0_Deployment",
            "CI",
            "release",
        ],
        "grades": {
            "MASTER-LESSONS-LEARNED": 3,
            "Power_Framework_v1.8.0_Deployment": 2,
        },
        "description": "GitHub Actions CI/CD"
    },
    {
        "id": "TC-09",
        "query": "VPN Tailscale network tunnel",
        "relevant": [
            "Successor-Hub",
            "network",
            "tailscale",
            "VPN",
        ],
        "grades": {
            "Successor-Hub": 3,
            "network": 2,
        },
        "description": "VPN / Tailscale networking"
    },
    {
        "id": "TC-10",
        "query": "firewall security hardening audit",
        "relevant": [
            "Global_Hardening_Audit",
            "MASTER-LESSONS-LEARNED",
            "firewall",
            "security",
        ],
        "grades": {
            "Global_Hardening_Audit": 3,
            "MASTER-LESSONS-LEARNED": 2,
            "security": 2,
        },
        "description": "Security hardening"
    },
    {
        "id": "TC-11",
        "query": "MCP server agent tool integration",
        "relevant": [
            "POWER_Framework",
            "AI-HomeLab",
            "MCP",
            "agent",
        ],
        "grades": {
            "POWER_Framework": 3,
            "AI-HomeLab": 2,
        },
        "description": "MCP / AI agent integration"
    },
    {
        "id": "TC-12",
        "query": "backup archive storage Samba",
        "relevant": [
            "Successor-Hub",
            "backup",
            "archive",
            "samba",
        ],
        "grades": {
            "Successor-Hub": 3,
            "archive": 1,
        },
        "description": "Backup & storage"
    },
    {
        "id": "TC-13",
        "query": "Power Safety Ukraine power outage",
        "relevant": [
            "Power-Safety-UA",
            "Release",
        ],
        "grades": {
            "Power-Safety-UA": 3,
            "Release": 2,
        },
        "description": "Domain-specific: Power-Safety-UA project"
    },
    {
        "id": "TC-14",
        "query": "embedding vector semantic search RAG",
        "relevant": [
            "POWER_Framework",
            "AI-HomeLab",
            "search",
        ],
        "grades": {
            "POWER_Framework": 3,
            "AI-HomeLab": 2,
        },
        "description": "Embedding / RAG search"
    },
    {
        "id": "TC-15",
        "query": "SSH port change configuration hardening",
        "relevant": [
            "SSH Port Changer",
            "Global_Hardening",
            "MASTER-LESSONS-LEARNED",
        ],
        "grades": {
            "SSH Port Changer": 3,
            "Global_Hardening": 2,
            "MASTER-LESSONS-LEARNED": 1,
        },
        "description": "SSH hardening"
    },
]

MODES = ["fts", "vector", "hybrid"]
K_VALUES = [1, 3, 5, 10]


def run_search(vault_path: str, query: str, mode: str, max_results: int = 10) -> list[dict]:
    """Run power search and return list of results with file paths."""
    cmd = [
        "power", "search", vault_path, query,
        "--mode", mode,
        "--max-results", str(max_results)
    ]
    try:
        t0 = time.perf_counter()
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60
        )
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


def is_relevant(result_path: str, relevant_keywords: list[str]) -> bool:
    """Check if result path contains any relevant keyword."""
    path_lower = result_path.lower()
    return any(kw.lower() in path_lower for kw in relevant_keywords)


def get_grade(result_path: str, grades: dict) -> int:
    """Get relevance grade for a result path."""
    path_lower = result_path.lower()
    max_grade = 0
    for keyword, grade in grades.items():
        if keyword.lower() in path_lower:
            max_grade = max(max_grade, grade)
    return max_grade


def precision_at_k(results: list, relevant: list, k: int) -> float:
    """Calculate Precision@K."""
    top_k = results[:k]
    hits = sum(1 for r in top_k if is_relevant(r["path"], relevant))
    return hits / k if k > 0 else 0.0


def recall_at_k(results: list, relevant: list, k: int) -> float:
    """Calculate Recall@K."""
    top_k = results[:k]
    hits = sum(1 for r in top_k if is_relevant(r["path"], relevant))
    return hits / len(relevant) if relevant else 0.0


def reciprocal_rank(results: list, relevant: list) -> float:
    """Calculate Reciprocal Rank for MRR."""
    for i, r in enumerate(results):
        if is_relevant(r["path"], relevant):
            return 1.0 / (i + 1)
    return 0.0


def dcg_at_k(results: list, grades: dict, k: int) -> float:
    """Calculate DCG@K."""
    dcg = 0.0
    for i, r in enumerate(results[:k]):
        grade = get_grade(r["path"], grades)
        if grade > 0:
            dcg += grade / math.log2(i + 2)
    return dcg


def idcg_at_k(grades: dict, k: int) -> float:
    """Calculate Ideal DCG@K."""
    sorted_grades = sorted(grades.values(), reverse=True)
    idcg = 0.0
    for i, grade in enumerate(sorted_grades[:k]):
        idcg += grade / math.log2(i + 2)
    return idcg


def ndcg_at_k(results: list, grades: dict, k: int) -> float:
    """Calculate nDCG@K."""
    dcg = dcg_at_k(results, grades, k)
    idcg = idcg_at_k(grades, k)
    return dcg / idcg if idcg > 0 else 0.0


def evaluate_mode(mode: str, test_cases: list) -> dict:
    """Evaluate all test cases for a given mode."""
    print(f"\n{'='*60}")
    print(f"  Evaluating mode: {mode.upper()}")
    print(f"{'='*60}")
    
    results_by_tc = {}
    total_latencies = []
    
    for tc in test_cases:
        print(f"  [{tc['id']}] {tc['description'][:50]}...", end=" ", flush=True)
        results, latency = run_search(VAULT_PATH, tc["query"], mode, max_results=10)
        total_latencies.append(latency)
        
        metrics = {}
        for k in K_VALUES:
            metrics[f"P@{k}"] = precision_at_k(results, tc["relevant"], k)
            metrics[f"R@{k}"] = recall_at_k(results, tc["relevant"], k)
            metrics[f"nDCG@{k}"] = ndcg_at_k(results, tc["grades"], k)
        metrics["RR"] = reciprocal_rank(results, tc["relevant"])
        metrics["latency"] = latency
        metrics["results_count"] = len(results)
        metrics["results"] = [r["path"] for r in results[:5]]
        
        results_by_tc[tc["id"]] = metrics
        
        hit_marker = "✓" if metrics["R@5"] > 0 else "✗"
        print(f"{hit_marker} R@5={metrics['R@5']:.2f} MRR={metrics['RR']:.2f} nDCG@5={metrics['nDCG@5']:.2f} ({latency:.2f}s)")
    
    # Aggregate metrics
    agg = {}
    for k in K_VALUES:
        agg[f"MAP@{k}"] = sum(m[f"P@{k}"] for m in results_by_tc.values()) / len(test_cases)
        agg[f"MAR@{k}"] = sum(m[f"R@{k}"] for m in results_by_tc.values()) / len(test_cases)
        agg[f"MnDCG@{k}"] = sum(m[f"nDCG@{k}"] for m in results_by_tc.values()) / len(test_cases)
    agg["MRR"] = sum(m["RR"] for m in results_by_tc.values()) / len(test_cases)
    agg["avg_latency"] = sum(total_latencies) / len(total_latencies)
    agg["p95_latency"] = sorted(total_latencies)[int(len(total_latencies) * 0.95)]
    
    return {"per_tc": results_by_tc, "aggregate": agg}


def main():
    print("=" * 60)
    print("  P.O.W.E.R. 2.0.3 — Search Quality Evaluation")
    print(f"  Vault: {VAULT_PATH}")
    print(f"  Test cases: {len(TEST_CASES)}")
    print(f"  Modes: {MODES}")
    print("=" * 60)
    
    # Check vault is accessible
    vault = Path(VAULT_PATH)
    if not vault.exists():
        print(f"ERROR: Vault not found at {VAULT_PATH}", file=sys.stderr)
        sys.exit(1)
    
    md_files = list(vault.rglob("*.md"))
    print(f"  Total .md files in vault: {len(md_files)}")
    
    all_results = {}
    
    for mode in MODES:
        all_results[mode] = evaluate_mode(mode, TEST_CASES)
    
    # ─── Print Summary Table ──────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  SUMMARY — Aggregate Metrics")
    print("=" * 80)
    
    header = f"{'Metric':<20}" + "".join(f"{m.upper():>15}" for m in MODES)
    print(header)
    print("-" * 80)
    
    metrics_to_show = [
        ("MRR", "MRR"),
        ("MAP@3", "MAP@3"),
        ("MAP@5", "MAP@5"),
        ("MAR@5", "MAR@5"),
        ("MAR@10", "MAR@10"),
        ("MnDCG@5", "MnDCG@5"),
        ("MnDCG@10", "MnDCG@10"),
        ("Avg Latency(s)", "avg_latency"),
        ("P95 Latency(s)", "p95_latency"),
    ]
    
    for label, key in metrics_to_show:
        row = f"{label:<20}"
        for mode in MODES:
            val = all_results[mode]["aggregate"].get(key, 0)
            row += f"{val:>15.3f}"
        print(row)
    
    # ─── Per-TC Table ────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  PER-QUERY R@5 (Recall at 5)")
    print("=" * 80)
    
    header2 = f"{'Test ID':<10}{'Description':<35}" + "".join(f"{m.upper():>12}" for m in MODES)
    print(header2)
    print("-" * 80)
    
    for tc in TEST_CASES:
        row = f"{tc['id']:<10}{tc['description'][:34]:<35}"
        for mode in MODES:
            val = all_results[mode]["per_tc"][tc["id"]]["R@5"]
            row += f"{val:>12.2f}"
        print(row)
    
    # Save raw results as JSON
    output_path = "/tmp/power_eval_results.json"
    with open(output_path, "w") as f:
        json.dump({
            "vault_files": len(md_files),
            "test_cases": len(TEST_CASES),
            "modes": MODES,
            "results": {
                mode: {
                    "aggregate": data["aggregate"],
                    "per_tc": {
                        tc_id: {
                            "metrics": {k: v for k, v in m.items() if k != "results"},
                            "top5": m["results"]
                        }
                        for tc_id, m in data["per_tc"].items()
                    }
                }
                for mode, data in all_results.items()
            }
        }, f, indent=2)
    
    print(f"\n  ✓ Raw results saved to: {output_path}")
    print("  Evaluation complete.")
    
    return all_results


if __name__ == "__main__":
    main()

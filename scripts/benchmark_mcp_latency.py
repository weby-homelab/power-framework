#!/usr/bin/env python3
"""MCP round-trip latency benchmark for POWER search modes.

Requires a running MCP server:
    POWER_VAULT_DIR=/root/gemma/brain POWER_MCP_TRANSPORT=http \\
    POWER_MCP_HOST=127.0.0.1 POWER_MCP_PORT=8765 \\
    python -m power_framework.mcp

Usage:
    python scripts/benchmark_mcp_latency.py
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

MODES = ["fts", "vector", "hybrid", "semantic", "reranked"]
ROUNDS = 10
SERVER_URL = "http://127.0.0.1:8765/mcp"


async def main() -> None:
    gt_path = Path("tests/fixtures/semantic_gt.json")
    if not gt_path.exists():
        print(f"ERROR: {gt_path} not found", file=sys.stderr)
        return 1

    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    queries = [item["query"] for item in gt["queries"]]

    try:
        from fastmcp import Client
    except ImportError:
        print("ERROR: fastmcp not installed (pip install fastmcp)", file=sys.stderr)
        return 1

    client = Client(SERVER_URL)

    async with client:
        for mode in MODES:
            # Warm-up, excluded from statistics.
            try:
                await client.call_tool(
                    "search_vault_tool",
                    {"query": queries[0], "max_results": 20, "search_mode": mode},
                    timeout=120,
                )
            except Exception as e:
                print(f"  {mode}: warmup failed ({e}) — skipping mode")
                continue

            values: list[float] = []
            for _ in range(ROUNDS):
                for query in queries:
                    started = time.perf_counter()
                    try:
                        await client.call_tool(
                            "search_vault_tool",
                            {"query": query, "max_results": 20, "search_mode": mode},
                            timeout=120,
                        )
                    except Exception as e:
                        print(f"  {mode}: query '{query}' failed: {e}", file=sys.stderr)
                        continue
                    elapsed = (time.perf_counter() - started) * 1000
                    values.append(elapsed)

            if not values:
                print(f"  {mode}: no successful measurements")
                continue

            values.sort()
            p50 = statistics.median(values)
            p95 = values[int(0.95 * (len(values) - 1))]
            p99 = values[int(0.99 * (len(values) - 1))]
            mean = statistics.mean(values)
            print(
                f"  {mode}: n={len(values)} p50={p50:.1f}ms p95={p95:.1f}ms "
                f"p99={p99:.1f}ms mean={mean:.1f}ms"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

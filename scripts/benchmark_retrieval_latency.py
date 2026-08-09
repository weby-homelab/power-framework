#!/usr/bin/env python3
"""Produce a content-free retrieval latency attribution receipt.

The benchmark deliberately reports timings and counts only. It never writes
queries, note paths, snippets, or note content to the receipt.

Examples:
    python scripts/benchmark_retrieval_latency.py --vault /path/to/vault
    python scripts/benchmark_retrieval_latency.py --vault /path/to/vault \
        --modes fts --rounds 5 --output latency.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from power_framework.core.metrics.udcg_real import _load_semantic_gt
from power_framework.core.searcher import search_vault
from power_framework.core.timing import collect_timings

DEFAULT_MODES = ("fts", "semantic", "hybrid", "reranked")
MCP_WORKER = Path(__file__).with_name("benchmark_retrieval_mcp_worker.py")


def _percentile(values: list[float], quantile: float) -> float | None:
    """Return a deterministic nearest-rank percentile."""
    if not values:
        return None
    rank = max(0, min(len(values) - 1, math.ceil(quantile * len(values)) - 1))
    return round(sorted(values)[rank], 3)


def _summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize wall and inclusive component timings without content."""
    wall = [float(sample["wall_ms"]) for sample in samples]
    components: dict[str, list[float]] = {}
    for sample in samples:
        for name, value in sample.get("timings_ms", {}).items():
            components.setdefault(name, []).append(float(value))

    return {
        "samples": len(samples),
        "wall_ms": {
            "p50": _percentile(wall, 0.50),
            "p95": _percentile(wall, 0.95),
            "mean": round(statistics.mean(wall), 3) if wall else None,
        },
        "components_ms": {
            name: {
                "samples": len(values),
                "p50": _percentile(values, 0.50),
                "p95": _percentile(values, 0.95),
                "mean": round(statistics.mean(values), 3),
            }
            for name, values in sorted(components.items())
        },
    }


def _load_queries(fixture: Path | None, limit: int) -> list[str]:
    queries = list(_load_semantic_gt(fixture))
    if not queries:
        raise ValueError("the benchmark query fixture is empty")
    return queries[:limit]


def _local_sample(vault: Path, query: str, mode: str, max_results: int) -> dict[str, Any]:
    started = time.perf_counter()
    with collect_timings() as receipt:
        results = search_vault(vault, query, max_results=max_results, mode=mode)
    return {
        "wall_ms": (time.perf_counter() - started) * 1000,
        "timings_ms": receipt.as_dict()["components_ms"],
        "result_count": len(results),
    }


def _subprocess_sample(vault: Path, query: str, mode: str, max_results: int) -> dict[str, Any]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--vault",
        str(vault),
        "--query",
        query,
        "--mode",
        mode,
        "--max-results",
        str(max_results),
    ]
    completed = subprocess.run(  # noqa: S603 - executable and arguments are local constants
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
        env=os.environ.copy(),
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()[-1:] or ["worker failed"]
        raise RuntimeError(f"cold worker failed for mode {mode}: {detail[0]}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("cold worker returned a non-JSON receipt") from exc
    if not isinstance(payload, dict) or "wall_ms" not in payload:
        raise RuntimeError("cold worker returned an invalid receipt")
    return payload


async def _mcp_samples(
    vault: Path,
    queries: list[str],
    mode: str,
    rounds: int,
    max_results: int,
) -> list[dict[str, Any]]:
    try:
        from fastmcp import Client
    except ImportError as exc:  # pragma: no cover - packaging gate covers this
        raise RuntimeError("fastmcp is required for the MCP latency shape") from exc

    with tempfile.TemporaryDirectory(prefix="power-timing-") as receipt_dir:
        receipt_path = Path(receipt_dir) / "receipt.json"
        environment = os.environ.copy()
        environment.update(
            {
                "POWER_VAULT_DIR": str(vault),
                "POWER_MCP_TRANSPORT": "stdio",
                "POWER_BENCHMARK_RECEIPT": str(receipt_path),
            }
        )
        config = {
            "mcpServers": {
                "power": {
                    "command": sys.executable,
                    "args": [str(MCP_WORKER.resolve())],
                    "env": environment,
                }
            }
        }
        samples: list[dict[str, Any]] = []
        async with Client(config) as client:
            warmup_query = queries[0]
            await client.call_tool(
                "search_vault_tool",
                {"query": warmup_query, "max_results": max_results, "search_mode": mode},
            )
            for _ in range(rounds):
                for query in queries:
                    started = time.perf_counter()
                    await client.call_tool(
                        "search_vault_tool",
                        {"query": query, "max_results": max_results, "search_mode": mode},
                    )
                    elapsed = (time.perf_counter() - started) * 1000
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                    samples.append(
                        {
                            "wall_ms": elapsed,
                            "timings_ms": receipt["components_ms"],
                        }
                    )
        return samples


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    vault = args.vault.expanduser().resolve()
    queries = _load_queries(args.fixture, args.query_limit)
    query_set_hash = hashlib.sha256("\0".join(queries).encode("utf-8")).hexdigest()
    receipt: dict[str, Any] = {
        "schema_version": "power.retrieval-latency.v1",
        "content_free": True,
        "query_set_sha256": query_set_hash,
        "controls": {
            "query_count": len(queries),
            "rounds": args.rounds,
            "max_results": args.max_results,
            "modes": args.modes,
        },
        "results": {},
        "errors": [],
    }

    for mode in args.modes:
        mode_result: dict[str, Any] = {}
        try:
            # One unrecorded request removes first-use sparse initialization from
            # the warm-process sample while preserving the cold-process shape.
            _local_sample(vault, queries[0], mode, args.max_results)
            warm = [
                _local_sample(vault, query, mode, args.max_results)
                for _ in range(args.rounds)
                for query in queries
            ]
            mode_result["warm_process"] = _summary(warm)
        except Exception as exc:
            receipt["errors"].append(f"{mode}/warm_process: {type(exc).__name__}: {exc}")

        try:
            cold = [
                _subprocess_sample(vault, query, mode, args.max_results)
                for _ in range(args.cold_rounds)
                for query in queries
            ]
            mode_result["cold_process"] = _summary(cold)
        except Exception as exc:
            receipt["errors"].append(f"{mode}/cold_process: {type(exc).__name__}: {exc}")

        try:
            mcp = await _mcp_samples(vault, queries, mode, args.rounds, args.max_results)
            mode_result["long_lived_mcp"] = _summary(mcp)
        except Exception as exc:
            receipt["errors"].append(f"{mode}/long_lived_mcp: {type(exc).__name__}: {exc}")

        receipt["results"][mode] = mode_result

    if receipt["errors"] and not receipt["results"]:
        raise RuntimeError("all retrieval latency modes failed")
    return receipt


def _worker(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    with collect_timings() as receipt:
        results = search_vault(
            args.vault.expanduser().resolve(),
            args.query,
            max_results=args.max_results,
            mode=args.mode,
        )
    json.dump(
        {
            "wall_ms": (time.perf_counter() - started) * 1000,
            "timings_ms": receipt.as_dict()["components_ms"],
            "result_count": len(results),
        },
        sys.stdout,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--modes", nargs="+", choices=DEFAULT_MODES, default=list(DEFAULT_MODES))
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--cold-rounds", type=int, default=1)
    parser.add_argument("--query-limit", type=int, default=4)
    parser.add_argument("--max-results", type=int, default=20)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--query", help=argparse.SUPPRESS)
    parser.add_argument("--mode", choices=DEFAULT_MODES, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.worker:
        if not args.query or not args.mode:
            parser.error("--worker requires --query and --mode")
        return _worker(args)
    if args.rounds < 1 or args.cold_rounds < 1 or args.query_limit < 1:
        parser.error("rounds and query-limit must be positive")

    payload = asyncio.run(_run(args))
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        sys.stdout.write(serialized)
    return 0 if not payload["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Produce a content-free retrieval latency and resource receipt.

The benchmark deliberately reports verified metadata, timings, resource
summaries, and counts only. It never writes queries, note paths, snippets, or
note content to the receipt.

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
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from power_framework.core.benchmark_resources import resource_snapshot
from power_framework.core.doctor import run_doctor
from power_framework.core.generation_index import resolve_active_generation
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

    resource_values: dict[str, list[int]] = {
        "peak_rss_bytes": [],
        "gpu_memory_used_bytes": [],
    }
    resource_scopes: set[str] = set()
    resource_sources: set[str] = set()
    for sample in samples:
        resources = sample.get("resources", {})
        if not isinstance(resources, dict):
            continue
        for name in resource_values:
            value = resources.get(name)
            if isinstance(value, int) and value >= 0:
                resource_values[name].append(value)
        scope = resources.get("gpu_memory_scope")
        source = resources.get("gpu_memory_source")
        if isinstance(scope, str):
            resource_scopes.add(scope)
        if isinstance(source, str):
            resource_sources.add(source)

    def resource_summary(values: list[int]) -> dict[str, int | float | None]:
        return {
            "samples": len(values),
            "p50": _percentile([float(value) for value in values], 0.50),
            "p95": _percentile([float(value) for value in values], 0.95),
            "max": max(values) if values else None,
        }

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
        "resources": {
            "peak_rss_bytes": resource_summary(resource_values["peak_rss_bytes"]),
            "gpu_memory_used_bytes": resource_summary(resource_values["gpu_memory_used_bytes"]),
            "gpu_memory_scope": sorted(resource_scopes) or None,
            "gpu_memory_source": sorted(resource_sources) or None,
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
        "resources": resource_snapshot(include_gpu=False),
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
                            "resources": receipt.get("resources", {}),
                        }
                    )
        return samples


def _index_identity(vault: Path) -> dict[str, Any]:
    """Read verified generation identity and dense manifest without user data."""
    try:
        active = resolve_active_generation(vault)
    except Exception as exc:
        return {"kind": "unreadable", "error_type": type(exc).__name__}
    if active is None:
        return {"kind": "legacy_db", "generation_id": None}

    try:
        with sqlite3.connect(f"file:{active.path.as_posix()}?mode=ro", uri=True) as connection:
            note_count = int(connection.execute("SELECT COUNT(*) FROM file_metadata").fetchone()[0])
            chunk_count = int(
                connection.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
            )
            manifest = dict(
                connection.execute(
                    "SELECT manifest_key, manifest_value FROM dense_index_manifest"
                ).fetchall()
            )
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        return {
            "kind": "unreadable",
            "generation_id": active.generation_id,
            "error_type": type(exc).__name__,
        }

    return {
        "kind": "immutable_generation",
        "generation_id": active.generation_id,
        "source_snapshot_hash": active.source_snapshot_hash,
        "database_sha256": active.db_sha256,
        "database_size_bytes": active.db_size,
        "indexed_notes": note_count,
        "indexed_chunks": chunk_count,
        "dense_manifest": {
            key: manifest[key]
            for key in ("embedding_provider", "embedding_model", "chunk_count")
            if key in manifest
        },
    }


def _provider_receipt(vault: Path, *, probe: bool) -> dict[str, Any]:
    """Return sanitized actual-provider state; never include doctor paths."""
    if not probe:
        return {"probe_requested": False, "binding": "not_requested"}
    try:
        report = run_doctor(vault, probe_embedding=True)
    except Exception as exc:
        return {
            "probe_requested": True,
            "binding": "failed",
            "error_type": type(exc).__name__,
        }
    embedding = report.get("embedding", {})
    if not isinstance(embedding, dict):
        return {
            "probe_requested": True,
            "binding": "failed",
            "error_type": "invalid_report",
        }
    issues = report.get("issues", [])
    issue_codes = [
        {"code": issue.get("code"), "severity": issue.get("severity")}
        for issue in issues
        if isinstance(issue, dict)
    ]
    available = embedding.get("available_providers", [])
    runtime = embedding.get("runtime")
    return {
        "probe_requested": True,
        "binding": embedding.get("binding"),
        "bound_provider": embedding.get("bound_provider"),
        "configured_provider": embedding.get("provider"),
        "requested_device": embedding.get("requested_device"),
        "available_providers": sorted(str(value) for value in available),
        "runtime_version": runtime.get("version") if isinstance(runtime, dict) else None,
        "probe_seconds": embedding.get("probe_seconds"),
        "issues": issue_codes,
    }


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    vault = args.vault.expanduser().resolve()
    queries = _load_queries(args.fixture, args.query_limit)
    query_set_hash = hashlib.sha256("\0".join(queries).encode("utf-8")).hexdigest()
    resource_start = resource_snapshot()
    receipt: dict[str, Any] = {
        "schema_version": "power.retrieval-latency.v2",
        "content_free": True,
        "query_set_sha256": query_set_hash,
        "index": _index_identity(vault),
        "provider": _provider_receipt(vault, probe=args.probe_provider),
        "controls": {
            "query_count": len(queries),
            "rounds": args.rounds,
            "max_results": args.max_results,
            "modes": args.modes,
        },
        "results": {},
        "errors": [],
    }

    if args.require_immutable_generation and receipt["index"].get("kind") != "immutable_generation":
        receipt["errors"].append(
            "index/immutable_generation: verified immutable generation required"
        )
    if args.require_provider_binding:
        provider = receipt["provider"]
        if provider.get("binding") != "verified" or not provider.get("bound_provider"):
            receipt["errors"].append("provider/binding: verified active provider required")

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

    receipt["resources"] = {
        "run_start": resource_start,
        "run_end": resource_snapshot(),
        "gpu_memory_note": "device-wide snapshots; may include unrelated processes",
    }
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
            "resources": resource_snapshot(include_gpu=False),
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
    parser.add_argument(
        "--probe-provider",
        action="store_true",
        help="Probe the actual embedding session and include sanitized provider state",
    )
    parser.add_argument(
        "--require-provider-binding",
        action="store_true",
        help="Fail unless the provider probe creates a session with an active provider",
    )
    parser.add_argument(
        "--require-immutable-generation",
        action="store_true",
        help="Fail unless the vault resolves to a verified immutable generation",
    )
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--query", help=argparse.SUPPRESS)
    parser.add_argument("--mode", choices=DEFAULT_MODES, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.worker:
        if not args.query or not args.mode:
            parser.error("--worker requires --query and --mode")
        return _worker(args)
    if args.require_provider_binding:
        args.probe_provider = True
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

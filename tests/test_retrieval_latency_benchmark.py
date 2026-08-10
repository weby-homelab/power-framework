"""Hermetic tests for the content-free retrieval latency benchmark."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).parents[1] / "scripts" / "benchmark_retrieval_latency.py"
SPEC = importlib.util.spec_from_file_location("benchmark_retrieval_latency", SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def test_percentile_is_nearest_rank() -> None:
    assert benchmark._percentile([3.0, 1.0, 2.0], 0.50) == 2.0
    assert benchmark._percentile([], 0.95) is None


def test_summary_contains_only_timings_and_counts() -> None:
    result = benchmark._summary(
        [
            {
                "wall_ms": 10.0,
                "timings_ms": {"sqlite_read": 2.0},
                "resources": {"peak_rss_bytes": 100, "gpu_memory_used_bytes": None},
            },
            {
                "wall_ms": 20.0,
                "timings_ms": {"sqlite_read": 4.0},
                "resources": {"peak_rss_bytes": 200, "gpu_memory_used_bytes": 300},
            },
        ]
    )

    assert result["samples"] == 2
    assert result["wall_ms"]["p50"] == 10.0
    assert result["components_ms"]["sqlite_read"]["p95"] == 4.0
    assert result["resources"]["peak_rss_bytes"]["max"] == 200
    assert result["resources"]["gpu_memory_used_bytes"]["p50"] == 300.0
    assert "query" not in result
    assert "snippet" not in result
    assert "path" not in result


def test_provider_receipt_is_sanitized(monkeypatch) -> None:
    monkeypatch.setattr(
        benchmark,
        "run_doctor",
        lambda vault, probe_embedding: {
            "embedding": {
                "binding": "verified",
                "bound_provider": "CPUExecutionProvider",
                "provider": "bge-m3",
                "requested_device": "auto",
                "available_providers": ["CPUExecutionProvider"],
                "runtime": {"version": "1.0"},
                "probe_seconds": 0.25,
            },
            "issues": [],
            "vault": {"path": "/private/path"},
        },
    )

    result = benchmark._provider_receipt(Path("/private/path"), probe=True)

    assert result["binding"] == "verified"
    assert result["bound_provider"] == "CPUExecutionProvider"
    assert "vault" not in result
    assert "/private/path" not in str(result)


def test_resource_snapshot_can_omit_device_probe() -> None:
    result = benchmark.resource_snapshot(include_gpu=False)

    assert set(result) == {
        "peak_rss_bytes",
        "gpu_memory_used_bytes",
        "gpu_memory_scope",
        "gpu_memory_source",
    }
    assert result["gpu_memory_used_bytes"] is None
    assert result["gpu_memory_scope"] is None
    assert result["gpu_memory_source"] is None


def test_index_identity_encodes_special_database_path(tmp_path, monkeypatch) -> None:
    database = tmp_path / "generation#1?verified.sqlite"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE file_metadata (rel_path TEXT)")
        connection.execute("CREATE TABLE chunk_embeddings (chunk_id TEXT)")
        connection.execute(
            "CREATE TABLE dense_index_manifest (manifest_key TEXT, manifest_value TEXT)"
        )
        connection.execute("INSERT INTO file_metadata VALUES ('03_Resources/note.md')")
        connection.execute("INSERT INTO chunk_embeddings VALUES ('chunk-1')")
        connection.execute("INSERT INTO dense_index_manifest VALUES ('chunk_count', '1')")
        connection.commit()

    monkeypatch.setattr(
        benchmark,
        "resolve_active_generation",
        lambda vault: SimpleNamespace(
            path=database,
            generation_id="generation-1",
            source_snapshot_hash="source-hash",
            db_sha256="database-sha",
            db_size=database.stat().st_size,
        ),
    )

    result = benchmark._index_identity(tmp_path)

    assert result["kind"] == "immutable_generation"
    assert result["indexed_notes"] == 1
    assert result["indexed_chunks"] == 1
    assert result["dense_manifest"] == {"chunk_count": "1"}


def test_receipt_errors_are_content_free(monkeypatch, tmp_path) -> None:
    marker = "query-marker /private/vault"
    args = argparse.Namespace(
        vault=tmp_path,
        fixture=None,
        query_limit=1,
        rounds=1,
        cold_rounds=1,
        max_results=1,
        modes=["fts"],
        probe_provider=False,
        require_provider_binding=False,
        require_immutable_generation=False,
    )
    monkeypatch.setattr(benchmark, "_load_queries", lambda fixture, limit: [marker])
    monkeypatch.setattr(
        benchmark,
        "_index_identity",
        lambda vault: {"kind": "legacy_db", "generation_id": None},
    )
    monkeypatch.setattr(
        benchmark,
        "_provider_receipt",
        lambda vault, probe: {"probe_requested": False, "binding": "not_requested"},
    )

    def fail_local(*args, **kwargs):
        raise RuntimeError(marker)

    monkeypatch.setattr(benchmark, "_local_sample", fail_local)
    monkeypatch.setattr(benchmark, "_subprocess_sample", fail_local)

    async def fail_mcp(*args, **kwargs):
        raise RuntimeError(marker)

    monkeypatch.setattr(benchmark, "_mcp_samples", fail_mcp)

    payload = asyncio.run(benchmark._run(args))

    assert payload["errors"] == [
        "fts/warm_process: RuntimeError",
        "fts/cold_process: RuntimeError",
        "fts/long_lived_mcp: RuntimeError",
    ]
    assert marker not in json.dumps(payload)

"""Hermetic tests for the content-free retrieval latency benchmark."""

from __future__ import annotations

import importlib.util
from pathlib import Path

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

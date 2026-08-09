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
            {"wall_ms": 10.0, "timings_ms": {"sqlite_read": 2.0}},
            {"wall_ms": 20.0, "timings_ms": {"sqlite_read": 4.0}},
        ]
    )

    assert result["samples"] == 2
    assert result["wall_ms"]["p50"] == 10.0
    assert result["components_ms"]["sqlite_read"]["p95"] == 4.0
    assert "query" not in result
    assert "snippet" not in result
    assert "path" not in result

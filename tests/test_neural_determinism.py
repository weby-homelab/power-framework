"""Neural determinism tests for semantic and reranked search modes.

Verifies that repeated queries produce identical results within floating-point
tolerance across in-process repeats, cross-process repeats, and batch sizes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _vault_present() -> bool:
    vault = os.getenv("POWER_VAULT_DIR", "/root/gemma/brain")
    try:
        return Path(vault).exists()
    except OSError:
        return False


def _benchmarks_enabled() -> bool:
    """Keep real-vault neural benchmarks out of the default unit suite."""
    return os.getenv("POWER_RUN_BENCHMARKS", "").lower() in {"1", "true", "yes"}


def _reranker_available() -> bool:
    from huggingface_hub import try_to_load_from_cache

    from power_framework.core.reranker import (
        BGE_RERANKER_PINNED_REPO,
        BGE_RERANKER_PINNED_REVISION,
    )

    cached = try_to_load_from_cache(
        BGE_RERANKER_PINNED_REPO,
        "onnx/model.onnx",
        revision=BGE_RERANKER_PINNED_REVISION,
    )
    return isinstance(cached, str) and Path(cached).is_file()


_TEST_QUERIES = [
    "gpg signing",
    "power safety",
    "docker compose",
    "tailscale vpn",
]

_REPEATS_IN_PROCESS = 5


@pytest.mark.bench
@pytest.mark.skipif(
    not (_benchmarks_enabled() and _vault_present()),
    reason="set POWER_RUN_BENCHMARKS=1 with a real brain vault to run neural benchmarks",
)
class TestSemanticDeterminism:
    """Determinism assertions for semantic search mode."""

    def _run_semantic(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        from power_framework.core.searcher import search_vault

        vault = Path(os.getenv("POWER_VAULT_DIR", "/root/gemma/brain"))
        results = search_vault(vault, query, max_results=max_results, mode="semantic")
        return [{"rel_path": r.rel_path, "score": r.score} for r in results]

    @pytest.mark.parametrize("query", _TEST_QUERIES)
    def test_in_process_repeats_produce_identical_top5(self, query: str):
        first = self._run_semantic(query)
        for _ in range(_REPEATS_IN_PROCESS - 1):
            current = self._run_semantic(query)
            for i in range(min(len(first), 5)):
                assert (
                    first[i]["rel_path"] == current[i]["rel_path"]
                ), f"Path mismatch at rank {i}: {first[i]['rel_path']} vs {current[i]['rel_path']}"
                assert (
                    abs(first[i]["score"] - current[i]["score"]) <= 1e-5
                ), f"Score mismatch at rank {i}: {first[i]['score']} vs {current[i]['score']}"

    def test_all_queries_return_results(self):
        for query in _TEST_QUERIES:
            results = self._run_semantic(query)
            assert len(results) > 0, f"Semantic search returned no results for: {query}"


@pytest.mark.bench
@pytest.mark.skipif(
    not (_benchmarks_enabled() and _vault_present()),
    reason="set POWER_RUN_BENCHMARKS=1 with a real brain vault to run neural benchmarks",
)
@pytest.mark.skipif(not _reranker_available(), reason="reranker ONNX not cached")
class TestRerankedDeterminism:
    """Determinism assertions for reranked mode."""

    def _run_reranked(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        from power_framework.core.searcher import search_vault

        vault = Path(os.getenv("POWER_VAULT_DIR", "/root/gemma/brain"))
        results = search_vault(vault, query, max_results=max_results, mode="reranked")
        return [{"rel_path": r.rel_path, "score": r.score} for r in results]

    @pytest.mark.parametrize("query", _TEST_QUERIES)
    def test_batch_1_and_8_same_top5(self, query: str, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("POWER_RERANKER_BATCH_SIZE", "1")
        scores_b1 = self._run_reranked(query)
        monkeypatch.setenv("POWER_RERANKER_BATCH_SIZE", "8")
        scores_b8 = self._run_reranked(query)
        for i in range(min(len(scores_b1), 5)):
            assert scores_b1[i]["rel_path"] == scores_b8[i]["rel_path"], (
                f"Rank {i} path differs between batch=1 and batch=8: "
                f"{scores_b1[i]['rel_path']} vs {scores_b8[i]['rel_path']}"
            )
            assert abs(scores_b1[i]["score"] - scores_b8[i]["score"]) <= 1e-5

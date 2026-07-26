"""Batch-size equivalence tests for BGEM3Reranker.

Verifies that batch_size=1 and batch_size=8 produce identical rankings
within floating-point tolerance, and that quality metrics are preserved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from power_framework.core.reranker import BGEM3Reranker, get_reranker

# Sample test documents spanning UA+EN topics with varying relevance.
_SAMPLE_QUERY = "українська мова semantic retrieval power framework"
_SAMPLE_DOCS = [
    "P.O.W.E.R. — AI-native Second Brain toolkit з підтримкою української мови",
    "Recipe for banana bread with walnuts and cinnamon",
    "BGE-M3 dense embeddings enable multilingual semantic retrieval across UA and EN",
    "Configuration guide for nginx reverse proxy with ssl termination",
    "How to set up Obsidian vault with P.A.R.A. methodology for knowledge management",
    "Server hardening with ufw firewall and fail2ban intrusion prevention",
    "Docker compose production deployment with healthcheck and auto-restart",
    "Tailscale mesh vpn subnet routing and acl configuration for homelab",
    "Python async programming patterns for high-performance i/o bound applications",
    "Linux systemd service unit file creation and management best practices",
]


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
    return _cached_model_file_exists(cached)


def _cached_model_file_exists(cached: object) -> bool:
    """Return true only for an existing cached model file, never a cache sentinel."""
    return isinstance(cached, str) and Path(cached).is_file()


def test_reranker_cache_none_is_unavailable():
    """A missing cache entry does not enable model-dependent tests."""
    assert not _cached_model_file_exists(None)


def test_reranker_cached_no_exist_is_unavailable():
    """Hugging Face's sentinel is not a filesystem path."""
    from huggingface_hub import _CACHED_NO_EXIST

    assert not _cached_model_file_exists(_CACHED_NO_EXIST)


def test_reranker_cached_model_path_is_available(tmp_path: Path):
    """A cached model is available only when its file is present."""
    model_path = tmp_path / "model.onnx"
    model_path.write_bytes(b"test")
    assert _cached_model_file_exists(str(model_path))


@pytest.mark.skipif(not _reranker_available(), reason="BGE reranker ONNX not cached")
class TestBGEM3RerankerBatchEquivalence:
    """Batch-size equivalence: per-document vs batch=8 must produce same ranking."""

    def _run_with_batch(self, monkeypatch: pytest.MonkeyPatch, batch_size: int) -> list[float]:
        monkeypatch.setenv("POWER_RERANKER_BATCH_SIZE", str(batch_size))
        # Re-create to pick up the env
        reranker = BGEM3Reranker()
        return reranker.rerank(_SAMPLE_QUERY, _SAMPLE_DOCS)

    def test_batch_1_and_8_same_ordering(self, monkeypatch: pytest.MonkeyPatch):
        scores_1 = self._run_with_batch(monkeypatch, 1)
        scores_8 = self._run_with_batch(monkeypatch, 8)

        assert len(scores_1) == len(scores_8) == len(_SAMPLE_DOCS)

        for i in range(len(_SAMPLE_DOCS)):
            assert (
                abs(scores_1[i] - scores_8[i]) <= 1e-5
            ), f"Score mismatch at doc {i}: batch1={scores_1[i]:.6f} batch8={scores_8[i]:.6f}"

    def test_batch_4_and_8_same_ordering(self, monkeypatch: pytest.MonkeyPatch):
        scores_4 = self._run_with_batch(monkeypatch, 4)
        scores_8 = self._run_with_batch(monkeypatch, 8)

        for i in range(len(_SAMPLE_DOCS)):
            assert (
                abs(scores_4[i] - scores_8[i]) <= 1e-5
            ), f"Score mismatch at doc {i}: batch4={scores_4[i]:.6f} batch8={scores_8[i]:.6f}"

    def test_batch_16_does_not_change_ordering(self, monkeypatch: pytest.MonkeyPatch):
        scores_1 = self._run_with_batch(monkeypatch, 1)
        scores_16 = self._run_with_batch(monkeypatch, 16)

        for i in range(len(_SAMPLE_DOCS)):
            assert (
                abs(scores_1[i] - scores_16[i]) <= 1e-5
            ), f"Score mismatch at doc {i}: batch1={scores_1[i]:.6f} batch16={scores_16[i]:.6f}"

    def test_rerank_preserves_doc_count(self):
        reranker = BGEM3Reranker()
        scores = reranker.rerank(_SAMPLE_QUERY, _SAMPLE_DOCS[:3])
        assert len(scores) == 3

    def test_empty_docs_returns_empty(self):
        reranker = BGEM3Reranker()
        assert reranker.rerank("query", []) == []

    def test_batch_1_returns_scores_for_each_doc(self, monkeypatch: pytest.MonkeyPatch):
        reranker = BGEM3Reranker()
        monkeypatch.setenv("POWER_RERANKER_BATCH_SIZE", "1")
        scores = reranker.rerank("test query", ["doc1", "doc2"])
        assert len(scores) == 2
        assert all(isinstance(s, float) for s in scores)


def test_default_batch_size_env(monkeypatch: pytest.MonkeyPatch):
    """The runtime fallback splits nine documents into batches of eight and one."""
    monkeypatch.delenv("POWER_RERANKER_BATCH_SIZE", raising=False)
    reranker = BGEM3Reranker()
    seen_batch_sizes: list[int] = []

    monkeypatch.setattr(reranker, "_lazy_init", lambda: None)

    def fake_rerank_batch(query: str, documents: list[str]) -> list[float]:
        seen_batch_sizes.append(len(documents))
        return [0.5] * len(documents)

    monkeypatch.setattr(reranker, "_rerank_batch", fake_rerank_batch)
    assert reranker.rerank("query", [f"doc-{index}" for index in range(9)]) == [0.5] * 9
    assert seen_batch_sizes == [8, 1]


def test_reranker_implements_protocol():
    """get_reranker() returns an object matching RerankerProtocol."""
    from power_framework.core.colbert_reranker import is_colbert_enabled

    if is_colbert_enabled():
        pytest.skip("colbert enabled, skipping BGE default check")
    reranker = get_reranker()
    assert hasattr(reranker, "rerank")
    assert callable(reranker.rerank)

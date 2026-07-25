"""Batch-size equivalence tests for BGEM3Reranker.

Verifies that batch_size=1 and batch_size=8 produce identical rankings
within floating-point tolerance, and that quality metrics are preserved.
"""

from __future__ import annotations

import os

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

    return (
        try_to_load_from_cache(
            BGE_RERANKER_PINNED_REPO,
            "onnx/model.onnx",
            revision=BGE_RERANKER_PINNED_REVISION,
        )
        is not None
    )


@pytest.mark.skipif(not _reranker_available(), reason="BGE reranker ONNX not cached")
class TestBGEM3RerankerBatchEquivalence:
    """Batch-size equivalence: per-document vs batch=8 must produce same ranking."""

    def _run_with_batch(self, batch_size: int) -> list[float]:
        os.environ["POWER_RERANKER_BATCH_SIZE"] = str(batch_size)
        # Re-create to pick up the env
        reranker = BGEM3Reranker()
        return reranker.rerank(_SAMPLE_QUERY, _SAMPLE_DOCS)

    def test_batch_1_and_8_same_ordering(self):
        scores_1 = self._run_with_batch(1)
        scores_8 = self._run_with_batch(8)

        assert len(scores_1) == len(scores_8) == len(_SAMPLE_DOCS)

        for i in range(len(_SAMPLE_DOCS)):
            assert (
                abs(scores_1[i] - scores_8[i]) <= 1e-5
            ), f"Score mismatch at doc {i}: batch1={scores_1[i]:.6f} batch8={scores_8[i]:.6f}"

    def test_batch_4_and_8_same_ordering(self):
        scores_4 = self._run_with_batch(4)
        scores_8 = self._run_with_batch(8)

        for i in range(len(_SAMPLE_DOCS)):
            assert (
                abs(scores_4[i] - scores_8[i]) <= 1e-5
            ), f"Score mismatch at doc {i}: batch4={scores_4[i]:.6f} batch8={scores_8[i]:.6f}"

    def test_batch_16_does_not_change_ordering(self):
        scores_1 = self._run_with_batch(1)
        scores_16 = self._run_with_batch(16)

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

    def test_batch_1_returns_scores_for_each_doc(self):
        reranker = BGEM3Reranker()
        os.environ["POWER_RERANKER_BATCH_SIZE"] = "1"
        scores = reranker.rerank("test query", ["doc1", "doc2"])
        assert len(scores) == 2
        assert all(isinstance(s, float) for s in scores)


def test_default_batch_size_env():
    """Default POWER_RERANKER_BATCH_SIZE should be 8."""
    import power_framework.core.reranker as rr

    assert rr.BGEM3Reranker._BATCH_SIZE == 8


def test_reranker_implements_protocol():
    """get_reranker() returns an object matching RerankerProtocol."""
    from power_framework.core.colbert_reranker import is_colbert_enabled

    if is_colbert_enabled():
        pytest.skip("colbert enabled, skipping BGE default check")
    reranker = get_reranker()
    assert hasattr(reranker, "rerank")
    assert callable(reranker.rerank)

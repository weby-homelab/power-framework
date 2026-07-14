"""Tests for EmbeddingManager."""

from __future__ import annotations

import pytest

from power_framework.core.embeddings import EMBEDDING_DIM, EmbeddingManager


class TestEmbeddingManager:
    def test_embed_single_text(self):
        manager = EmbeddingManager()
        vec = manager.embed("Hello world")
        assert isinstance(vec, list)
        assert len(vec) == EMBEDDING_DIM
        assert all(isinstance(v, float) for v in vec)

    def test_embed_batch(self):
        manager = EmbeddingManager()
        texts = ["Hello world", "Second test text", "Third one here"]
        vectors = manager.embed_batch(texts)
        assert len(vectors) == 3
        for vec in vectors:
            assert isinstance(vec, list)
            assert len(vec) == EMBEDDING_DIM
            assert all(isinstance(v, float) for v in vec)

    def test_embed_empty_string(self):
        manager = EmbeddingManager()
        vec = manager.embed("")
        assert isinstance(vec, list)
        assert len(vec) == EMBEDDING_DIM

    def test_embed_batch_empty(self):
        manager = EmbeddingManager()
        vectors = manager.embed_batch([])
        assert vectors == []

    def test_embedding_deterministic(self):
        manager = EmbeddingManager()
        vec1 = manager.embed("Some consistent text")
        vec2 = manager.embed("Some consistent text")
        assert vec1 == vec2

    def test_embedding_different_texts(self):
        manager = EmbeddingManager()
        vec1 = manager.embed("Kittens are cute")
        vec2 = manager.embed("Rocket science")
        assert vec1 != vec2

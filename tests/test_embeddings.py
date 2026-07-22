"""Tests for EmbeddingManager."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

import power_framework.core.embeddings as embeddings

if TYPE_CHECKING:
    from pathlib import Path


class TestEmbeddingManager:
    def test_import_has_no_hardcoded_env_file_side_effect(self):
        assert "/root/geminicli/.env" not in inspect.getsource(embeddings)

    def test_embed_single_text(self):
        manager = embeddings.get_embedding_manager()
        vec = manager.embed("Hello world")
        assert isinstance(vec, list)
        assert len(vec) == manager.dimension
        assert all(isinstance(v, float) for v in vec)

    def test_embed_batch(self):
        manager = embeddings.get_embedding_manager()
        texts = ["Hello world", "Second test text", "Third one here"]
        vectors = manager.embed_batch(texts)
        assert len(vectors) == 3
        for vec in vectors:
            assert isinstance(vec, list)
            assert len(vec) == manager.dimension
            assert all(isinstance(v, float) for v in vec)

    def test_embed_empty_string(self):
        manager = embeddings.get_embedding_manager()
        vec = manager.embed("")
        assert isinstance(vec, list)
        assert len(vec) == manager.dimension

    def test_embed_batch_empty(self):
        manager = embeddings.get_embedding_manager()
        vectors = manager.embed_batch([])
        assert vectors == []

    def test_embedding_deterministic(self):
        manager = embeddings.get_embedding_manager()
        vec1 = manager.embed("Some consistent text")
        vec2 = manager.embed("Some consistent text")
        assert vec1 == vec2

    def test_embedding_different_texts(self):
        manager = embeddings.get_embedding_manager()
        vec1 = manager.embed("Kittens are cute")
        vec2 = manager.embed("Rocket science")
        assert vec1 != vec2

    def test_canonical_identity_contains_immutable_revision(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("POWER_EMBED_PROVIDER", "bge-m3")
        provider, model = embeddings.configured_embedding_identity()
        assert provider == "BGEM3OnnxManager"
        assert model == f"{embeddings.BGE_M3_PINNED_REPO}@{embeddings.BGE_M3_ONNX_REVISION}"

    def test_sha256_verification_fails_closed(self, tmp_path: Path):
        artifact = tmp_path / "model.onnx"
        artifact.write_bytes(b"tampered")

        with pytest.raises(RuntimeError, match=r"model_sha256_mismatch:model\.onnx"):
            embeddings._verify_sha256(str(artifact), "0" * 64)

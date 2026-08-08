"""Tests for EmbeddingManager."""

from __future__ import annotations

import inspect
import signal
from typing import TYPE_CHECKING

import pytest

import power_framework.core.embeddings as embeddings

if TYPE_CHECKING:
    from pathlib import Path


class TestEmbeddingManager:
    def test_auto_device_prefers_cuda_and_keeps_cpu_fallback(self, monkeypatch: pytest.MonkeyPatch):
        class FakeOrt:
            @staticmethod
            def get_available_providers():
                return ["CPUExecutionProvider", "CUDAExecutionProvider"]

        monkeypatch.setenv("POWER_EMBED_DEVICE", "auto")
        providers = embeddings.select_onnx_providers(FakeOrt())
        assert providers[0][0] == "CUDAExecutionProvider"
        assert providers[-1][0] == "CPUExecutionProvider"

    def test_explicit_unavailable_device_fails_closed(self, monkeypatch: pytest.MonkeyPatch):
        class FakeOrt:
            @staticmethod
            def get_available_providers():
                return ["CPUExecutionProvider"]

        monkeypatch.setenv("POWER_EMBED_DEVICE", "cuda")
        with pytest.raises(RuntimeError, match="requested_onnx_provider_unavailable"):
            embeddings.select_onnx_providers(FakeOrt())

    def test_preload_dlls_is_called_before_probing_providers(self, monkeypatch: pytest.MonkeyPatch):
        """Availability is meaningless until the GPU runtime DLLs are loadable."""
        calls: list[str] = []

        class FakeOrt:
            @staticmethod
            def preload_dlls():
                calls.append("preload")

            @staticmethod
            def get_available_providers():
                calls.append("probe")
                return ["CPUExecutionProvider"]

        monkeypatch.setenv("POWER_EMBED_DEVICE", "cpu")
        embeddings.select_onnx_providers(FakeOrt())
        assert calls == ["preload", "probe"]

    def test_missing_preload_dlls_is_tolerated(self, monkeypatch: pytest.MonkeyPatch):
        """Older onnxruntime builds have no preload_dlls(); that must not break."""

        class FakeOrt:
            @staticmethod
            def get_available_providers():
                return ["CPUExecutionProvider"]

        monkeypatch.setenv("POWER_EMBED_DEVICE", "cpu")
        assert embeddings.select_onnx_providers(FakeOrt())

    def test_gpu_downgraded_to_cpu_at_session_creation_fails_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """A provider can be listed and still fail to load; only the session knows."""

        class FakeSession:
            @staticmethod
            def get_providers():
                return ["CPUExecutionProvider"]

        monkeypatch.setenv("POWER_EMBED_DEVICE", "cuda")
        providers: list[object] = [
            ("CUDAExecutionProvider", {}),
            ("CPUExecutionProvider", {}),
        ]
        with pytest.raises(RuntimeError, match="requested_onnx_provider_not_bound"):
            embeddings.verify_bound_provider(FakeSession(), providers, "POWER_EMBED_DEVICE")

    def test_auto_may_fall_back_to_cpu_without_raising(self, monkeypatch: pytest.MonkeyPatch):
        """Under `auto` a CPU binding is the documented fallback, not a failure.

        `auto` still puts the GPU provider first in the list, so inspecting the
        request list alone cannot tell an auto fallback from an explicit
        downgrade — the mode has to be read.
        """

        class FakeSession:
            @staticmethod
            def get_providers():
                return ["CPUExecutionProvider"]

        monkeypatch.setenv("POWER_EMBED_DEVICE", "auto")
        providers: list[object] = [("CUDAExecutionProvider", {}), ("CPUExecutionProvider", {})]
        assert (
            embeddings.verify_bound_provider(FakeSession(), providers, "POWER_EMBED_DEVICE")
            == "CPUExecutionProvider"
        )

    def test_rocm_provider_name_is_matched_case_insensitively(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """A build may spell it differently from our constant; exact match then
        silently reports the device as unavailable on a working ROCm host."""

        class FakeOrt:
            @staticmethod
            def get_available_providers():
                return ["ROCmExecutionProvider", "CPUExecutionProvider"]

        monkeypatch.setenv("POWER_EMBED_DEVICE", "rocm")
        providers = embeddings.select_onnx_providers(FakeOrt())
        # The name ORT reported wins, not our constant.
        assert providers[0][0] == "ROCmExecutionProvider"
        assert providers[0][1]["device_id"] == 0

    def test_auto_selects_rocm_regardless_of_spelling(self, monkeypatch: pytest.MonkeyPatch):
        class FakeOrt:
            @staticmethod
            def get_available_providers():
                return ["ROCmExecutionProvider", "CPUExecutionProvider"]

        monkeypatch.setenv("POWER_EMBED_DEVICE", "auto")
        providers = embeddings.select_onnx_providers(FakeOrt())
        assert providers[0][0] == "ROCmExecutionProvider"
        assert providers[0][1]["device_id"] == 0

    def test_bound_gpu_provider_is_accepted(self, monkeypatch: pytest.MonkeyPatch):
        class FakeSession:
            @staticmethod
            def get_providers():
                return ["CUDAExecutionProvider", "CPUExecutionProvider"]

        monkeypatch.setenv("POWER_EMBED_DEVICE", "cuda")
        providers: list[object] = [("CUDAExecutionProvider", {}), ("CPUExecutionProvider", {})]
        assert (
            embeddings.verify_bound_provider(FakeSession(), providers, "POWER_EMBED_DEVICE")
            == "CUDAExecutionProvider"
        )

    def test_explicit_cpu_is_not_treated_as_a_downgrade(self, monkeypatch: pytest.MonkeyPatch):
        class FakeSession:
            @staticmethod
            def get_providers():
                return ["CPUExecutionProvider"]

        monkeypatch.setenv("POWER_EMBED_DEVICE", "cpu")
        providers: list[object] = [("CPUExecutionProvider", {})]
        assert (
            embeddings.verify_bound_provider(FakeSession(), providers, "POWER_EMBED_DEVICE")
            == "CPUExecutionProvider"
        )

    def test_ollama_attempt_does_not_require_sigalrm(self, monkeypatch: pytest.MonkeyPatch):
        manager = embeddings.OllamaEmbeddingManager()
        monkeypatch.delattr(signal, "SIGALRM", raising=False)
        assert manager._do_attempt(lambda: "ok") == ("ok", None)

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

    def test_unknown_provider_fails_closed(self, monkeypatch: pytest.MonkeyPatch):
        """WTF #3 remediation: an unknown POWER_EMBED_PROVIDER must raise
        RuntimeError instead of silently falling back to a default backend."""
        monkeypatch.setenv("POWER_EMBED_PROVIDER", "totally-unknown-backend")
        with pytest.raises(RuntimeError, match=r"unknown_embed_provider"):
            embeddings.get_embedding_manager()

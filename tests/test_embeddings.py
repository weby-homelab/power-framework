"""Tests for EmbeddingManager."""

from __future__ import annotations

import inspect
import signal
import sys
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING

import pytest

import power_framework.core.embeddings as embeddings

if TYPE_CHECKING:
    from pathlib import Path


class TestEmbeddingManager:
    def test_dense_readiness_is_read_only_and_reports_missing_snapshot(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "cache"))

        ready, reason = embeddings.dense_embedding_ready()

        assert ready is False
        assert reason in {"model_snapshot_missing", "optional_dependency_missing"}
        assert not (tmp_path / "cache").exists()

    def test_dense_readiness_accepts_complete_local_snapshot(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = (
            tmp_path / "models--aapot--bge-m3-onnx" / "snapshots" / embeddings.BGE_M3_ONNX_REVISION
        )
        snapshot.mkdir(parents=True)
        for filename in ("model.onnx", "model.onnx.data", "tokenizer.json"):
            (snapshot / filename).write_bytes(b"cached")
        monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))

        ready, reason = embeddings.dense_embedding_ready()

        assert ready is True
        assert reason == "ready"

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

    def test_preload_dlls_runs_before_provider_probe(self, monkeypatch: pytest.MonkeyPatch):
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

    def test_missing_preload_dlls_does_not_break_cpu(self, monkeypatch: pytest.MonkeyPatch):
        class FakeOrt:
            @staticmethod
            def get_available_providers():
                return ["CPUExecutionProvider"]

        monkeypatch.setenv("POWER_EMBED_DEVICE", "cpu")
        assert embeddings.select_onnx_providers(FakeOrt())[0][0] == "CPUExecutionProvider"

    def test_rocm_provider_name_is_resolved_case_insensitively(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        class FakeOrt:
            @staticmethod
            def get_available_providers():
                return ["ROCmExecutionProvider", "CPUExecutionProvider"]

        monkeypatch.setenv("POWER_EMBED_DEVICE", "rocm")
        providers = embeddings.select_onnx_providers(FakeOrt())
        assert providers[0][0] == "ROCmExecutionProvider"
        assert providers[0][1]["device_id"] == 0

    def test_directml_provider_can_be_selected_and_verified(self, monkeypatch: pytest.MonkeyPatch):
        class FakeOrt:
            @staticmethod
            def get_available_providers():
                return ["DmlExecutionProvider", "CPUExecutionProvider"]

        monkeypatch.setenv("POWER_EMBED_DEVICE", "directml")
        providers = embeddings.select_onnx_providers(FakeOrt())
        assert providers[0][0] == "DmlExecutionProvider"
        assert (
            embeddings.verify_bound_provider(
                self._fake_session(["DmlExecutionProvider", "CPUExecutionProvider"]),
                providers,
                "POWER_EMBED_DEVICE",
            )
            == "DmlExecutionProvider"
        )

    def test_preload_failure_is_visible_but_not_fatal_for_cpu(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ):
        class FakeOrt:
            @staticmethod
            def preload_dlls():
                raise OSError("missing optional GPU runtime")

            @staticmethod
            def get_available_providers():
                return ["CPUExecutionProvider"]

        monkeypatch.setenv("POWER_EMBED_DEVICE", "cpu")
        with caplog.at_level("WARNING"):
            providers = embeddings.select_onnx_providers(FakeOrt())
        assert providers[0][0] == "CPUExecutionProvider"
        assert "preload_dlls() failed" in caplog.text

    def test_ollama_attempt_does_not_require_sigalrm(self, monkeypatch: pytest.MonkeyPatch):
        manager = embeddings.OllamaEmbeddingManager()
        monkeypatch.delattr(signal, "SIGALRM", raising=False)
        assert manager._do_attempt(lambda: "ok") == ("ok", None)

    def test_ollama_rejects_unsafe_configured_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_ollama = ModuleType("ollama")
        fake_ollama.embed = lambda **_kwargs: SimpleNamespace(embeddings=[[1.0]])
        monkeypatch.setitem(sys.modules, "ollama", fake_ollama)
        monkeypatch.setenv("OLLAMA_HOST", "http://169.254.169.254/latest")

        with pytest.raises(PermissionError, match="Ollama endpoint"):
            embeddings.OllamaEmbeddingManager().embed("synthetic")

    def test_import_has_no_hardcoded_env_file_side_effect(self):
        assert "/root/geminicli/.env" not in inspect.getsource(embeddings)

    def test_embed_single_text(self, fake_bge_manager):
        manager = fake_bge_manager
        vec = manager.embed("Hello world")
        assert isinstance(vec, list)
        assert len(vec) == manager.dimension
        assert all(isinstance(v, float) for v in vec)

    def test_embed_batch(self, fake_bge_manager):
        manager = fake_bge_manager
        texts = ["Hello world", "Second test text", "Third one here"]
        vectors = manager.embed_batch(texts)
        assert len(vectors) == 3
        for vec in vectors:
            assert isinstance(vec, list)
            assert len(vec) == manager.dimension
            assert all(isinstance(v, float) for v in vec)

    def test_embed_empty_string(self, fake_bge_manager):
        manager = fake_bge_manager
        vec = manager.embed("")
        assert isinstance(vec, list)
        assert len(vec) == manager.dimension

    def test_embed_batch_empty(self, fake_bge_manager):
        manager = fake_bge_manager
        vectors = manager.embed_batch([])
        assert vectors == []

    def test_embedding_deterministic(self, fake_bge_manager):
        manager = fake_bge_manager
        vec1 = manager.embed("Some consistent text")
        vec2 = manager.embed("Some consistent text")
        assert vec1 == vec2

    def test_embedding_different_texts(self, fake_bge_manager):
        manager = fake_bge_manager
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

    @staticmethod
    def _fake_session(providers: list[str]):
        class FakeSession:
            @staticmethod
            def get_providers():
                return providers

        return FakeSession()

    def test_explicit_gpu_binding_must_match_requested_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("POWER_EMBED_DEVICE", "cuda")
        providers: list[object] = [
            ("CUDAExecutionProvider", {}),
            ("CPUExecutionProvider", {}),
        ]
        with pytest.raises(RuntimeError, match="requested_onnx_provider_not_bound"):
            embeddings.verify_bound_provider(
                self._fake_session(["ROCmExecutionProvider", "CPUExecutionProvider"]),
                providers,
                "POWER_EMBED_DEVICE",
            )

    def test_auto_cpu_fallback_is_visible_but_allowed(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("POWER_EMBED_DEVICE", "auto")
        providers: list[object] = [
            ("CUDAExecutionProvider", {}),
            ("CPUExecutionProvider", {}),
        ]
        assert (
            embeddings.verify_bound_provider(
                self._fake_session(["CPUExecutionProvider"]),
                providers,
                "POWER_EMBED_DEVICE",
            )
            == "CPUExecutionProvider"
        )

    def test_explicit_gpu_binding_is_case_insensitive(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("POWER_EMBED_DEVICE", "cuda")
        providers: list[object] = [("CUDAExecutionProvider", {}), ("CPUExecutionProvider", {})]
        assert (
            embeddings.verify_bound_provider(
                self._fake_session(["CUDAExecutionProvider", "CPUExecutionProvider"]),
                providers,
                "POWER_EMBED_DEVICE",
            )
            == "CUDAExecutionProvider"
        )

    def test_explicit_cpu_binding_is_checked(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("POWER_EMBED_DEVICE", "cpu")
        providers: list[object] = [("CPUExecutionProvider", {})]
        assert (
            embeddings.verify_bound_provider(
                self._fake_session(["CPUExecutionProvider"]),
                providers,
                "POWER_EMBED_DEVICE",
            )
            == "CPUExecutionProvider"
        )

    def test_explicit_gpu_empty_binding_fails_closed(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("POWER_EMBED_DEVICE", "cuda")
        providers: list[object] = [("CUDAExecutionProvider", {}), ("CPUExecutionProvider", {})]
        with pytest.raises(RuntimeError, match="requested_onnx_provider_not_bound"):
            embeddings.verify_bound_provider(
                self._fake_session([]), providers, "POWER_EMBED_DEVICE"
            )

    def test_requested_device_inherits_embedding_mode_for_reranker(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("POWER_RERANKER_DEVICE", raising=False)
        monkeypatch.setenv("POWER_EMBED_DEVICE", " CUDA ")
        assert embeddings.requested_device("POWER_RERANKER_DEVICE") == "cuda"
        monkeypatch.setenv("POWER_RERANKER_DEVICE", "")
        assert embeddings.requested_device("POWER_RERANKER_DEVICE") == "auto"

    def test_failed_binding_does_not_retain_an_unsafe_embedder_session(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        class FakeOptions:
            pass

        class FakeSession:
            def __init__(self, *args: object, **kwargs: object):
                pass

            @staticmethod
            def get_providers():
                return ["CPUExecutionProvider"]

        fake_ort = ModuleType("onnxruntime")
        fake_ort.SessionOptions = FakeOptions
        fake_ort.InferenceSession = FakeSession
        fake_ort.get_available_providers = lambda: [
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        ]
        fake_hub = ModuleType("huggingface_hub")
        fake_hub.hf_hub_download = lambda *args, **kwargs: "unused-model-file"
        fake_tokenizers = ModuleType("tokenizers")
        fake_tokenizers.Tokenizer = object
        monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)
        monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)
        monkeypatch.setitem(sys.modules, "tokenizers", fake_tokenizers)
        monkeypatch.setenv("POWER_EMBED_DEVICE", "cuda")
        monkeypatch.setenv("POWER_ALLOW_UNVERIFIED_MODELS", "1")

        manager = embeddings.BGEM3OnnxManager(repo="example/repo", revision="dev")
        with pytest.raises(RuntimeError, match="requested_onnx_provider_not_bound"):
            manager.embed("provider probe")
        assert manager._session is None
        assert manager.active_provider is None

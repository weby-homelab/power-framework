"""Tests for EmbeddingManager."""

from __future__ import annotations

import hashlib
import inspect
import os
import signal
import sys
import threading
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import power_framework.core.embeddings as embeddings


class TestEmbeddingManager:
    def test_dense_readiness_is_read_only_and_reports_missing_snapshot(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("POWER_EMBED_PROVIDER", "bge-m3")
        monkeypatch.setenv("POWER_BGE_M3_ONNX_REPO", embeddings.BGE_M3_PINNED_REPO)
        monkeypatch.setenv("POWER_BGE_M3_ONNX_REVISION", embeddings.BGE_M3_PINNED_REVISION)
        monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "cache"))

        ready, reason = embeddings.dense_embedding_ready()

        assert ready is False
        assert reason in {"model_snapshot_missing", "optional_dependency_missing"}
        assert not (tmp_path / "cache").exists()

    def test_dense_readiness_accepts_complete_local_snapshot(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("POWER_EMBED_PROVIDER", "bge-m3")
        monkeypatch.setenv("POWER_BGE_M3_ONNX_REPO", embeddings.BGE_M3_PINNED_REPO)
        monkeypatch.setenv("POWER_BGE_M3_ONNX_REVISION", embeddings.BGE_M3_PINNED_REVISION)
        snapshot = (
            tmp_path
            / "models--aapot--bge-m3-onnx"
            / "snapshots"
            / embeddings.BGE_M3_PINNED_REVISION
        )
        snapshot.mkdir(parents=True)
        expected_hashes: dict[str, str] = {}
        for filename in ("model.onnx", "model.onnx.data", "tokenizer.json"):
            content = f"cached:{filename}".encode()
            (snapshot / filename).write_bytes(content)
            expected_hashes[filename] = hashlib.sha256(content).hexdigest()
        monkeypatch.setattr(embeddings, "BGE_M3_FILE_SHA256", expected_hashes)
        monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))

        ready, reason = embeddings.dense_embedding_ready()

        assert ready is True
        assert reason == "ready"

    def test_dense_readiness_rejects_unapproved_model_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("POWER_EMBED_PROVIDER", "bge-m3")
        monkeypatch.setenv("POWER_BGE_M3_ONNX_REPO", "custom/model")
        monkeypatch.setenv("POWER_BGE_M3_ONNX_REVISION", "b" * 40)
        monkeypatch.delenv("POWER_ALLOW_CUSTOM_MODELS", raising=False)
        monkeypatch.delenv("POWER_MODEL_APPROVAL", raising=False)

        ready, reason = embeddings.dense_embedding_ready()

        assert ready is False
        assert reason == "model_approval_required"

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

    def test_fastembed_inference_does_not_set_process_offline_flags(self, monkeypatch):
        """A local model must not change the process policy while embedding."""
        observed_flags: list[tuple[str | None, ...]] = []

        class FakeModel:
            def embed(self, texts, **_kwargs):
                observed_flags.append(
                    tuple(os.getenv(name) for name in ("POWER_MODEL_OFFLINE", "HF_HUB_OFFLINE"))
                )
                return iter([[float(len(text))] for text in texts])

        for name in ("POWER_MODEL_OFFLINE", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
            monkeypatch.delenv(name, raising=False)
        manager = embeddings.FastEmbedManager()
        manager._model = FakeModel()

        assert manager.embed("text") == [4.0]
        assert manager.embed_batch(["a", "bb"]) == [[1.0], [2.0]]
        assert observed_flags == [(None, None), (None, None)]

    def test_fastembed_uses_registered_name_and_specific_local_snapshot_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FastEmbed receives a supported identity plus the verified local directory."""
        from power_framework.core import model_policy

        root = tmp_path / "power-model-fastembed-api"
        root.mkdir()
        spec = model_policy.ApprovedModel(
            repo="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            revision="a" * 40,
            provider="fastembed-embedding",
            license="MIT",
            files=(),
            canonical=False,
        )
        prepared = model_policy.PreparedModel(spec, {}, str(root))
        monkeypatch.setattr(embeddings, "prepare_external_model", lambda **_kwargs: prepared)
        captured: dict[str, object] = {}

        class FakeEmbedding:
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)

        fastembed = ModuleType("fastembed")
        fastembed.TextEmbedding = FakeEmbedding  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "fastembed", fastembed)

        manager = embeddings.FastEmbedManager(
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2@" + "a" * 40
        )
        manager._lazy_init()

        assert (
            captured["model_name"] == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        assert captured["specific_model_path"] == str(root)
        manager.close()
        assert not root.exists()

    def test_installed_fastembed_accepts_specific_local_snapshot_path(self, tmp_path: Path) -> None:
        """The real FastEmbed API accepts a registered name plus local path."""
        from fastembed import TextEmbedding

        from power_framework.core.model_policy import force_model_offline

        with force_model_offline():
            loader = TextEmbedding(
                model_name=embeddings.FASTEMBED_MODEL,
                specific_model_path=str(tmp_path),
                lazy_load=True,
            )

        assert loader.model_name == embeddings.FASTEMBED_MODEL

    def test_fastembed_lazy_init_is_single_flight_and_owns_one_staging_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Concurrent initialization prepares and constructs exactly one model."""
        from power_framework.core import model_policy

        prepared_models: list[model_policy.PreparedModel] = []
        prepare_calls = 0

        def prepare(**_kwargs: object) -> model_policy.PreparedModel:
            nonlocal prepare_calls
            prepare_calls += 1
            root = tmp_path / f"power-model-fastembed-{prepare_calls}"
            root.mkdir()
            spec = model_policy.ApprovedModel(
                repo="custom/model",
                revision="a" * 40,
                provider="fastembed-embedding",
                license="MIT",
                files=(),
                canonical=False,
            )
            prepared = model_policy.PreparedModel(spec, {}, str(root))
            prepared_models.append(prepared)
            return prepared

        constructor_started = threading.Event()
        release_constructor = threading.Event()
        constructor_calls = 0

        class BlockingEmbedding:
            def __init__(self, **_kwargs: object) -> None:
                nonlocal constructor_calls
                constructor_calls += 1
                if constructor_calls == 1:
                    constructor_started.set()
                    if not release_constructor.wait(5):
                        raise AssertionError("constructor release was not signalled")

        fastembed = ModuleType("fastembed")
        fastembed.TextEmbedding = BlockingEmbedding  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "fastembed", fastembed)
        monkeypatch.setattr(embeddings, "prepare_external_model", prepare)

        manager = embeddings.FastEmbedManager("custom/model@" + "a" * 40)
        start_barrier = threading.Barrier(2)
        errors: list[Exception] = []

        def initialize() -> None:
            try:
                start_barrier.wait(timeout=5)
                manager._lazy_init()
            except Exception as exc:  # pragma: no cover - assertion below reports the failure
                errors.append(exc)

        workers = [threading.Thread(target=initialize) for _ in range(2)]
        for worker in workers:
            worker.start()
        assert constructor_started.wait(5)
        release_constructor.set()
        for worker in workers:
            worker.join(timeout=5)

        assert all(not worker.is_alive() for worker in workers)
        assert not errors
        assert prepare_calls == 1
        assert constructor_calls == 1
        assert len(prepared_models) == 1
        assert Path(prepared_models[0].local_reference).is_dir()

        manager.close()
        assert not Path(prepared_models[0].local_reference).exists()

    def test_fastembed_constructor_failure_releases_staging_and_retry_is_fresh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed constructor cannot poison retry state or retain its staging tree."""
        from power_framework.core import model_policy

        prepared_models: list[model_policy.PreparedModel] = []

        def prepare(**_kwargs: object) -> model_policy.PreparedModel:
            root = tmp_path / f"power-model-retry-{len(prepared_models) + 1}"
            root.mkdir()
            spec = model_policy.ApprovedModel(
                repo="custom/model",
                revision="a" * 40,
                provider="fastembed-embedding",
                license="MIT",
                files=(),
                canonical=False,
            )
            prepared = model_policy.PreparedModel(spec, {}, str(root))
            prepared_models.append(prepared)
            return prepared

        constructor_calls = 0

        class RetryEmbedding:
            def __init__(self, **_kwargs: object) -> None:
                nonlocal constructor_calls
                constructor_calls += 1
                if constructor_calls == 1:
                    raise RuntimeError("synthetic constructor failure")

        fastembed = ModuleType("fastembed")
        fastembed.TextEmbedding = RetryEmbedding  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "fastembed", fastembed)
        monkeypatch.setattr(embeddings, "prepare_external_model", prepare)

        manager = embeddings.FastEmbedManager("custom/model@" + "a" * 40)
        with pytest.raises(RuntimeError, match="synthetic constructor failure"):
            manager._lazy_init()

        assert manager._model is None
        assert not Path(prepared_models[0].local_reference).exists()

        manager._lazy_init()
        assert manager._model is not None
        assert len(prepared_models) == 2
        assert not Path(prepared_models[0].local_reference).exists()
        assert Path(prepared_models[1].local_reference).is_dir()

        manager.close()
        manager.close()
        assert not Path(prepared_models[1].local_reference).exists()

    def test_qwen_probe_failure_releases_staging_and_retry_is_fresh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed eager probe releases its tree and permits one clean retry."""
        from power_framework.core import model_policy

        prepared_models: list[model_policy.PreparedModel] = []

        def prepare(**_kwargs: object) -> model_policy.PreparedModel:
            root = tmp_path / f"power-model-qwen-retry-{len(prepared_models) + 1}"
            root.mkdir()
            spec = model_policy.ApprovedModel(
                repo="custom/model",
                revision="a" * 40,
                provider="qwen3-embedding-onnx",
                license="MIT",
                files=(),
                canonical=False,
            )
            prepared = model_policy.PreparedModel(spec, {}, str(root))
            prepared_models.append(prepared)
            return prepared

        instances = 0
        constructor_kwargs: dict[str, object] = {}

        class RetryQwenEmbedding:
            def __init__(self, **_kwargs: object) -> None:
                nonlocal instances
                instances += 1
                self.instance = instances
                constructor_kwargs.update(_kwargs)

            def embed(self, _texts, **_kwargs: object):
                if self.instance == 1:
                    raise RuntimeError("synthetic probe failure")
                return iter([[0.0] * 1024])

        qwen = ModuleType("qwen3_embed")
        qwen.TextEmbedding = RetryQwenEmbedding  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "qwen3_embed", qwen)
        monkeypatch.setattr(embeddings, "prepare_external_model", prepare)

        manager = embeddings.Qwen3EmbeddingManager("custom/model@" + "a" * 40)
        with pytest.raises(RuntimeError, match="qwen3_onnx_alloc_failed"):
            manager._lazy_init()

        assert manager._model is None
        assert not Path(prepared_models[0].local_reference).exists()

        manager._lazy_init()
        assert manager._model is not None
        assert len(prepared_models) == 2
        assert not Path(prepared_models[0].local_reference).exists()
        assert Path(prepared_models[1].local_reference).is_dir()
        assert constructor_kwargs["model_name"] == "custom/model"
        assert constructor_kwargs["specific_model_path"] == prepared_models[1].local_reference
        assert constructor_kwargs["local_files_only"] is True

        manager.close()
        manager.close()
        assert not Path(prepared_models[1].local_reference).exists()

    def test_canonical_identity_contains_immutable_revision(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("POWER_EMBED_PROVIDER", "bge-m3")
        monkeypatch.setenv("POWER_BGE_M3_ONNX_REPO", embeddings.BGE_M3_PINNED_REPO)
        monkeypatch.setenv("POWER_BGE_M3_ONNX_REVISION", embeddings.BGE_M3_PINNED_REVISION)
        provider, model = embeddings.configured_embedding_identity()
        assert provider == "BGEM3OnnxManager"
        assert model == f"{embeddings.BGE_M3_PINNED_REPO}@{embeddings.BGE_M3_PINNED_REVISION}"

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
        from power_framework.core import model_policy

        for name in model_policy.MODEL_OFFLINE_ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv("HF_ENDPOINT", raising=False)

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
        monkeypatch.setenv("POWER_EMBED_PROVIDER", "bge-m3")
        monkeypatch.setenv("POWER_EMBED_DEVICE", "cuda")
        monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-public")
        monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})
        monkeypatch.setattr(
            model_policy,
            "_verify_model_files",
            lambda _spec, paths: dict(paths),
        )

        manager = embeddings.BGEM3OnnxManager(
            repo=embeddings.BGE_M3_PINNED_REPO,
            revision=embeddings.BGE_M3_PINNED_REVISION,
        )
        with pytest.raises(RuntimeError, match="requested_onnx_provider_not_bound"):
            manager.embed("provider probe")
        assert manager._session is None
        assert manager.active_provider is None

    @pytest.mark.parametrize("failure_stage", ["tokenizer", "probe"])
    def test_bge_probe_failure_clears_session_and_allows_clean_retry(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure_stage: str
    ) -> None:
        """Direct BGE probe failures must not poison the manager's retry state."""
        model_files = {
            "model.onnx": str(tmp_path / "model.onnx"),
            "model.onnx.data": str(tmp_path / "model.onnx.data"),
            "tokenizer.json": str(tmp_path / "tokenizer.json"),
        }
        monkeypatch.setattr(embeddings, "acquire_model_files", lambda **_kwargs: model_files)

        class FakeOptions:
            enable_cpu_mem_arena = True
            intra_op_num_threads = 0
            inter_op_num_threads = 0

        class FakeSession:
            @staticmethod
            def get_providers() -> list[str]:
                return ["CPUExecutionProvider"]

        class FakeOrt:
            SessionOptions = FakeOptions
            InferenceSession = staticmethod(lambda *_args, **_kwargs: FakeSession())

            @staticmethod
            def get_available_providers() -> list[str]:
                return ["CPUExecutionProvider"]

        tokenizer_calls = 0

        class FakeTokenizer:
            @staticmethod
            def from_file(_path: str) -> FakeTokenizer:
                nonlocal tokenizer_calls
                tokenizer_calls += 1
                if failure_stage == "tokenizer" and tokenizer_calls == 1:
                    raise RuntimeError("synthetic BGE tokenizer failure")
                return FakeTokenizer()

            def enable_truncation(self, **_kwargs: int) -> None:
                return None

        tokenizers = ModuleType("tokenizers")
        tokenizers.Tokenizer = FakeTokenizer  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "onnxruntime", FakeOrt)
        monkeypatch.setitem(sys.modules, "tokenizers", tokenizers)
        monkeypatch.setenv("POWER_EMBED_DEVICE", "cpu")

        manager = embeddings.BGEM3OnnxManager(
            repo=embeddings.BGE_M3_PINNED_REPO,
            revision=embeddings.BGE_M3_PINNED_REVISION,
        )
        should_fail = True

        def probe(_texts: list[str]) -> list[list[float]]:
            if should_fail:
                raise RuntimeError("synthetic BGE probe failure")
            return [[0.0] * embeddings.BGE_M3_DIM]

        monkeypatch.setattr(manager, "_embed_raw", probe)
        expected_error = (
            "synthetic BGE tokenizer failure"
            if failure_stage == "tokenizer"
            else "synthetic BGE probe failure"
        )
        with pytest.raises(RuntimeError, match=expected_error):
            manager._lazy_init()
        assert manager._session is None
        assert manager._tokenizer is None
        assert manager.active_provider is None

        should_fail = False
        manager._lazy_init()
        assert manager._session is not None
        assert manager._tokenizer is not None

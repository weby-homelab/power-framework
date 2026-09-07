"""Tests for the RerankerManager class."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest
from huggingface_hub import try_to_load_from_cache

from power_framework.core.model_policy import MODEL_OFFLINE_ENV_VARS, ModelApprovalError
from power_framework.core.reranker import (
    ALLOW_NONCOMMERCIAL_MODELS_ENV,
    BGE_RERANKER_FILE_SHA256,
    BGE_RERANKER_PINNED_REPO,
    BGE_RERANKER_PINNED_REVISION,
    BGEM3Reranker,
    LexicalReranker,
    NonCommercialModelDisabledError,
    RerankerManager,
    get_reranker,
)
from power_framework.experimental import reranker as reranker_module


def _prepared_stub(tmp_path: Path, index: int, provider: str):
    """Create a real owned staging stub for delegated-loader lifecycle tests."""
    from power_framework.core.model_policy import ApprovedModel, PreparedModel

    root = tmp_path / f"power-model-reranker-{index}"
    root.mkdir()
    spec = ApprovedModel(
        repo="custom/model",
        revision="a" * 40,
        provider=provider,
        license="MIT",
        files=(),
        canonical=False,
    )
    return PreparedModel(spec, {}, str(root))


def _bge_reranker_available() -> bool:
    """True only if the BGE reranker ONNX snapshot is already cached locally."""
    return all(
        isinstance(
            cached := try_to_load_from_cache(
                BGE_RERANKER_PINNED_REPO,
                filename,
                revision=BGE_RERANKER_PINNED_REVISION,
            ),
            str,
        )
        and Path(cached).is_file()
        for filename in ("onnx/model.onnx", "onnx/model.onnx_data", "tokenizer.json")
    )


def _install_hf_download_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Install a local HF double so policy tests cannot perform real egress."""
    calls: list[str] = []
    module = ModuleType("huggingface_hub")

    def download(_repo: str, filename: str, **_kwargs: object) -> str:
        calls.append(filename)
        return "unexpected-model-file"

    module.hf_hub_download = download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)
    return calls


class TestRerankerManager:
    """Tests for RerankerManager."""

    def test_rerank_returns_scores(self):
        manager = RerankerManager()
        mock_model = MagicMock()
        mock_model.rerank.return_value = [0.9, 0.3, 0.7]
        manager._model = mock_model

        scores = manager.rerank("test query", ["doc1", "doc2", "doc3"])
        assert len(scores) == 3
        assert scores == [0.9, 0.3, 0.7]

    def test_rerank_orders_by_relevance(self):
        manager = RerankerManager()
        mock_model = MagicMock()
        mock_model.rerank.return_value = [0.3, 0.9, 0.7]
        manager._model = mock_model

        scores = manager.rerank("test query", ["doc1", "doc2", "doc3"])
        assert scores[1] > scores[0]
        assert scores[1] > scores[2]

    def test_rerank_single_document(self):
        manager = RerankerManager()
        mock_model = MagicMock()
        mock_model.rerank.return_value = [0.85]
        manager._model = mock_model

        scores = manager.rerank("test query", ["single doc"])
        assert len(scores) == 1
        assert scores[0] == 0.85

    def test_rerank_empty_documents(self):
        manager = RerankerManager()
        mock_model = MagicMock()
        mock_model.rerank.return_value = []
        manager._model = mock_model

        scores = manager.rerank("test query", [])
        assert scores == []

    def test_lazy_init_does_not_load_on_construction(self):
        manager = RerankerManager()
        assert manager._model is None

    def test_jina_requires_explicit_noncommercial_opt_in(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv(ALLOW_NONCOMMERCIAL_MODELS_ENV, raising=False)
        manager = RerankerManager()

        with pytest.raises(NonCommercialModelDisabledError, match=r"CC-BY-NC-4\.0"):
            manager._lazy_init()

    def test_rerank_calls_model_rerank_with_args(self):
        manager = RerankerManager()
        mock_model = MagicMock()
        mock_model.rerank.return_value = [0.5, 0.8]
        manager._model = mock_model

        manager.rerank("query", ["doc a", "doc b"])
        mock_model.rerank.assert_called_once_with("query", ["doc a", "doc b"])

    def test_delegated_rerank_inference_does_not_set_process_offline_flags(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A constructed delegated reranker must run without global policy mutation."""
        observed_flags: list[tuple[str | None, ...]] = []

        class FakeModel:
            def rerank(self, _query: str, _documents: list[str]) -> list[float]:
                observed_flags.append(
                    tuple(
                        os.getenv(name)
                        for name in (
                            "POWER_MODEL_OFFLINE",
                            "HF_HUB_OFFLINE",
                            "TRANSFORMERS_OFFLINE",
                        )
                    )
                )
                return [0.5]

        for name in ("POWER_MODEL_OFFLINE", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
            monkeypatch.delenv(name, raising=False)
        manager = RerankerManager()
        manager._model = FakeModel()

        assert manager.rerank("query", ["document"]) == [0.5]
        assert observed_flags == [(None, None, None)]

    def test_jina_constructor_failure_releases_owned_staging(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Jina import/constructor failure must not leak its prepared snapshot."""
        prepared_models = []

        def prepare(**_kwargs: object):
            prepared = _prepared_stub(tmp_path, len(prepared_models) + 1, "jina-reranker")
            prepared_models.append(prepared)
            return prepared

        constructor_args: dict[str, object] = {}

        class FailingCrossEncoder:
            def __init__(self, **_kwargs: object) -> None:
                constructor_args.update(_kwargs)
                raise RuntimeError("synthetic Jina constructor failure")

        cross_encoder = ModuleType("fastembed.rerank.cross_encoder")
        cross_encoder.TextCrossEncoder = FailingCrossEncoder  # type: ignore[attr-defined]
        rerank_package = ModuleType("fastembed.rerank")
        fastembed_package = ModuleType("fastembed")
        rerank_package.cross_encoder = cross_encoder  # type: ignore[attr-defined]
        fastembed_package.rerank = rerank_package  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "fastembed", fastembed_package)
        monkeypatch.setitem(sys.modules, "fastembed.rerank", rerank_package)
        monkeypatch.setitem(sys.modules, "fastembed.rerank.cross_encoder", cross_encoder)
        monkeypatch.setattr(reranker_module, "prepare_external_model", prepare)
        monkeypatch.setenv("POWER_RERANKER", "jina")
        monkeypatch.setenv(ALLOW_NONCOMMERCIAL_MODELS_ENV, "1")
        monkeypatch.setenv("POWER_EMBED_PROVIDER", "bge-m3")

        manager = RerankerManager("custom/model@" + "a" * 40)
        with pytest.raises(RuntimeError, match="synthetic Jina constructor failure"):
            manager._lazy_init()

        assert manager._model is None
        assert not Path(prepared_models[0].local_reference).exists()
        assert constructor_args["specific_model_path"] == prepared_models[0].local_reference

    def test_installed_fastembed_cross_encoder_accepts_specific_local_snapshot_path(
        self, tmp_path: Path
    ) -> None:
        """The real FastEmbed cross-encoder accepts the verified local path seam."""
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        from power_framework.core.model_policy import force_model_offline

        with force_model_offline():
            loader = TextCrossEncoder(
                model_name="jinaai/jina-reranker-v2-base-multilingual",
                specific_model_path=str(tmp_path),
                lazy_load=True,
            )

        assert loader.model_name == "jinaai/jina-reranker-v2-base-multilingual"

    def test_qwen_reranker_constructor_failure_releases_owned_staging(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Qwen3 reranker constructor failure must release the local snapshot."""
        prepared_models = []

        def prepare(**_kwargs: object):
            prepared = _prepared_stub(tmp_path, len(prepared_models) + 1, "qwen3-reranker-onnx")
            prepared_models.append(prepared)
            return prepared

        constructor_args: dict[str, object] = {}

        class FailingCrossEncoder:
            def __init__(self, **_kwargs: object) -> None:
                constructor_args.update(_kwargs)
                raise RuntimeError("synthetic Qwen reranker failure")

        qwen = ModuleType("qwen3_embed")
        qwen.TextCrossEncoder = FailingCrossEncoder  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "qwen3_embed", qwen)
        monkeypatch.setattr(reranker_module, "prepare_external_model", prepare)
        monkeypatch.setenv("POWER_RERANKER", "jina")
        monkeypatch.setenv(ALLOW_NONCOMMERCIAL_MODELS_ENV, "1")
        monkeypatch.setenv("POWER_EMBED_PROVIDER", "qwen3")
        monkeypatch.setenv("POWER_QWEN3_RERANKER_MODEL", "custom/model@" + "a" * 40)

        manager = RerankerManager("custom/model@" + "a" * 40)
        with pytest.raises(RuntimeError, match="synthetic Qwen reranker failure"):
            manager._lazy_init()

        assert manager._model is None
        assert not Path(prepared_models[0].local_reference).exists()
        assert constructor_args["model_name"] == "custom/model"
        assert constructor_args["specific_model_path"] == prepared_models[0].local_reference
        assert constructor_args["local_files_only"] is True

    def test_colbert_constructor_failure_releases_owned_staging(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ColBERT constructor failure must release its prepared snapshot."""
        from power_framework.experimental import colbert_reranker as colbert_module

        prepared_models = []

        def prepare(**_kwargs: object):
            prepared = _prepared_stub(tmp_path, len(prepared_models) + 1, "colbert-reranker")
            prepared_models.append(prepared)
            return prepared

        class FakeConfig:
            pass

        class FailingCheckpoint:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                raise RuntimeError("synthetic ColBERT constructor failure")

        infra = ModuleType("colbert.infra")
        infra.ColBERTConfig = FakeConfig  # type: ignore[attr-defined]
        checkpoint = ModuleType("colbert.modeling.checkpoint")
        checkpoint.Checkpoint = FailingCheckpoint  # type: ignore[attr-defined]
        modeling = ModuleType("colbert.modeling")
        modeling.checkpoint = checkpoint  # type: ignore[attr-defined]
        colbert = ModuleType("colbert")
        colbert.infra = infra  # type: ignore[attr-defined]
        colbert.modeling = modeling  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "colbert", colbert)
        monkeypatch.setitem(sys.modules, "colbert.infra", infra)
        monkeypatch.setitem(sys.modules, "colbert.modeling", modeling)
        monkeypatch.setitem(sys.modules, "colbert.modeling.checkpoint", checkpoint)
        monkeypatch.setattr(colbert_module, "prepare_external_model", prepare)
        monkeypatch.setattr(colbert_module, "_available_ram_gb", lambda: 16.0)
        monkeypatch.setenv("POWER_RERANKER", "colbert")

        manager = colbert_module.ColBERTLateInteractionReranker("custom/model@" + "a" * 40)
        with pytest.raises(RuntimeError, match="synthetic ColBERT constructor failure"):
            manager._lazy_init()

        assert manager._model is None
        assert not Path(prepared_models[0].local_reference).exists()

    def test_colbert_helpers(self):
        from unittest.mock import patch

        from power_framework.core.colbert_reranker import (
            _available_ram_gb,
            is_colbert_enabled,
        )

        ram = _available_ram_gb()
        assert isinstance(ram, float)

        with patch("builtins.open", side_effect=OSError("File not found")):
            assert _available_ram_gb() == 0.0

        assert isinstance(is_colbert_enabled(), bool)

    def test_colbert_reranker_exceptions(self):
        from unittest.mock import patch

        import pytest

        from power_framework.core.colbert_reranker import (
            ColBERTLateInteractionReranker,
            ColBERTUnavailableError,
        )

        with (
            patch.dict("os.environ", {"POWER_RERANKER": ""}),
            pytest.raises(ColBERTUnavailableError, match="opt-in"),
        ):
            ColBERTLateInteractionReranker()

        with (
            patch.dict("os.environ", {"POWER_RERANKER": "colbert"}),
            patch(
                "power_framework.core.colbert_reranker._available_ram_gb",
                return_value=1.0,
            ),
            pytest.raises(ColBERTUnavailableError, match="requires >="),
        ):
            ColBERTLateInteractionReranker()

        with (
            patch.dict("os.environ", {"POWER_RERANKER": "colbert"}),
            patch(
                "power_framework.core.colbert_reranker._available_ram_gb",
                return_value=16.0,
            ),
        ):
            colbert = ColBERTLateInteractionReranker()
            assert colbert.model_name is not None

    def test_lazy_init_already_initialized(self):
        manager = RerankerManager()
        mock_model = MagicMock()
        manager._model = mock_model
        manager._lazy_init()

    def test_get_reranker_default_is_bge(self):
        from unittest.mock import patch

        from power_framework.core.reranker import BGEM3Reranker

        # POWER 3.2: canonical default reranker is the MIT/Apache BGEM3Reranker.
        with patch(
            "power_framework.core.colbert_reranker.is_colbert_enabled",
            return_value=False,
        ):
            r = get_reranker()
            assert isinstance(r, BGEM3Reranker)

        with (
            patch(
                "power_framework.core.colbert_reranker.is_colbert_enabled",
                return_value=True,
            ),
            patch(
                "power_framework.core.colbert_reranker._available_ram_gb",
                return_value=1.0,
            ),
        ):
            r = get_reranker()
            assert isinstance(r, BGEM3Reranker)

    def test_bge_default_uses_a_pinned_snapshot_and_complete_file_hashes(self):
        assert BGE_RERANKER_PINNED_REPO == "onnx-community/bge-reranker-v2-m3-ONNX"
        assert len(BGE_RERANKER_PINNED_REVISION) == 40
        assert set(BGE_RERANKER_FILE_SHA256) == {
            "model.onnx",
            "model.onnx_data",
            "tokenizer.json",
        }
        assert all(len(digest) == 64 for digest in BGE_RERANKER_FILE_SHA256.values())

    def test_jina_opt_in_requires_both_flags(self, monkeypatch: pytest.MonkeyPatch):
        """Jina is only reachable when POWER_RERANKER=jina AND the NC flag is set."""
        monkeypatch.delenv(ALLOW_NONCOMMERCIAL_MODELS_ENV, raising=False)
        monkeypatch.delenv("POWER_RERANKER", raising=False)
        with pytest.raises(NonCommercialModelDisabledError, match=r"CC-BY-NC-4\.0"):
            RerankerManager()._lazy_init()

        monkeypatch.setenv(ALLOW_NONCOMMERCIAL_MODELS_ENV, "1")
        monkeypatch.delenv("POWER_RERANKER", raising=False)
        with pytest.raises(NonCommercialModelDisabledError, match=r"CC-BY-NC-4\.0"):
            RerankerManager()._lazy_init()

    def test_lexical_reranker_ranks_by_overlap(self):
        """License-clean fallback reranker needs no model download."""
        reranker = LexicalReranker()
        docs = [
            "Cats are small domesticated mammals",
            "A completely unrelated paragraph about rocket propulsion and orbitals",
            "The cat sat on the mat near the kitten",
        ]
        scores = reranker.rerank("cat kitten", docs)
        assert scores[0] > scores[1]
        assert scores[2] > scores[1]
        assert all(0.0 <= s <= 1.0 for s in scores)

    @pytest.mark.real_neural
    def test_bgem3_reranker_ranks_relevant_first(self):
        """Real BGE reranker ranking (skipped if the ONNX snapshot is not cached)."""
        if not _bge_reranker_available():
            pytest.skip("BGE reranker ONNX snapshot not available in this environment")
        reranker = BGEM3Reranker()
        docs = [
            "P.O.W.E.R. — AI-native Second Brain toolkit з підтримкою української мови",
            "Recipe for banana bread with walnuts and cinnamon",
            "BGE-M3 dense embeddings enable multilingual semantic retrieval",
        ]
        scores = reranker.rerank("українська мова semantic retrieval", docs)
        assert scores[0] + scores[2] > 0
        # The UA↔EN semantic query should favor the knowledge-base passages.
        assert scores[0] > scores[1]

    def test_qwen3_reranker_requires_model_policy_before_import(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        from unittest.mock import patch

        import pytest

        from power_framework.core import model_policy
        from power_framework.core.reranker import RerankerManager

        for name in MODEL_OFFLINE_ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        for name in (
            "HF_ENDPOINT",
            "POWER_EGRESS_POLICY",
            "POWER_ALLOW_CUSTOM_MODELS",
            "POWER_MODEL_APPROVAL",
            "POWER_QWEN3_RERANKER_MODEL",
        ):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-public")
        monkeypatch.setattr(
            reranker_module, "QWEN3_RERANKER_MODEL", "n24q02m/Qwen3-Reranker-0.6B-ONNX"
        )
        monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})
        calls = _install_hf_download_spy(monkeypatch)

        with (
            patch.dict(
                "os.environ",
                {
                    "POWER_EMBED_PROVIDER": "qwen3",
                    "POWER_RERANKER": "jina",
                    ALLOW_NONCOMMERCIAL_MODELS_ENV: "1",
                },
            ),
            patch.dict(sys.modules, {"qwen3_embed": None}),
        ):
            mgr = RerankerManager()
            with pytest.raises(ModelApprovalError, match="immutable_model_revision_required"):
                mgr._lazy_init()
        assert calls == []

    def test_fastembed_reranker_requires_model_policy_before_import(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        from unittest.mock import patch

        import pytest

        from power_framework.core import model_policy
        from power_framework.core.reranker import (
            ALLOW_NONCOMMERCIAL_MODELS_ENV,
            RerankerManager,
        )

        for name in MODEL_OFFLINE_ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        for name in (
            "HF_ENDPOINT",
            "POWER_EGRESS_POLICY",
            "POWER_ALLOW_CUSTOM_MODELS",
            "POWER_MODEL_APPROVAL",
            "POWER_JINA_RERANKER_MODEL",
        ):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-public")
        monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})
        calls = _install_hf_download_spy(monkeypatch)

        with (
            patch.dict(
                "os.environ",
                {
                    ALLOW_NONCOMMERCIAL_MODELS_ENV: "1",
                    "POWER_EMBED_PROVIDER": "bge-m3",
                    "POWER_RERANKER": "jina",
                },
            ),
            patch.dict(sys.modules, {"fastembed.rerank.cross_encoder": None}),
        ):
            mgr = RerankerManager()
            with pytest.raises(ModelApprovalError, match="custom_model_requires_approval"):
                mgr._lazy_init()
        assert calls == []

    def test_colbert_rerank_with_mock_model(self):
        from unittest.mock import MagicMock, patch

        from power_framework.core.colbert_reranker import ColBERTLateInteractionReranker

        with (
            patch.dict("os.environ", {"POWER_RERANKER": "colbert"}),
            patch(
                "power_framework.core.colbert_reranker._available_ram_gb",
                return_value=16.0,
            ),
        ):
            reranker = ColBERTLateInteractionReranker()
            mock_model = MagicMock()
            mock_sim = MagicMock()
            mock_max_sim = MagicMock()
            mock_max_sim.sum.return_value = 2.5
            mock_sim.max.return_value.values = mock_max_sim

            q_tokens = MagicMock()
            d_tokens = MagicMock()
            q_tokens.__matmul__.return_value = mock_sim
            q_tokens.T = MagicMock()

            mock_model.query.return_value = q_tokens
            mock_model.doc.return_value = d_tokens
            reranker._model = mock_model

            scores = reranker.rerank("q", ["doc1"])
            assert scores == [2.5]


def test_bge_reranker_probe_failure_clears_session_and_allows_clean_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Direct BGE reranker probe failures must leave retryable state."""
    model_files = {
        "onnx/model.onnx": str(tmp_path / "model.onnx"),
        "onnx/model.onnx_data": str(tmp_path / "model.onnx_data"),
        "tokenizer.json": str(tmp_path / "tokenizer.json"),
    }
    monkeypatch.setattr(reranker_module, "acquire_model_files", lambda **_kwargs: model_files)

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

    class FakeTokenizer:
        @staticmethod
        def from_file(_path: str) -> FakeTokenizer:
            return FakeTokenizer()

        def enable_truncation(self, max_length: int) -> None:
            del max_length

    tokenizers = ModuleType("tokenizers")
    tokenizers.Tokenizer = FakeTokenizer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "onnxruntime", FakeOrt)
    monkeypatch.setitem(sys.modules, "tokenizers", tokenizers)
    monkeypatch.setenv("POWER_RERANKER_DEVICE", "cpu")

    manager = BGEM3Reranker(
        repo=BGE_RERANKER_PINNED_REPO,
        revision=BGE_RERANKER_PINNED_REVISION,
    )
    should_fail = True

    def probe(_query: str, _document: str) -> list[float] | None:
        if should_fail:
            raise RuntimeError("synthetic BGE reranker probe failure")
        return [0.5]

    monkeypatch.setattr(manager, "_rerank_raw", probe)
    with pytest.raises(RuntimeError, match="synthetic BGE reranker probe failure"):
        manager._lazy_init()
    assert manager._session is None
    assert manager._tokenizer is None
    assert manager.active_provider is None

    should_fail = False
    manager._lazy_init()
    assert manager._session is not None
    assert manager._tokenizer is not None


def test_bge_reranker_omits_token_type_ids_when_model_does_not_accept_it():
    from unittest.mock import MagicMock

    from power_framework.core.reranker import BGEM3Reranker

    reranker = BGEM3Reranker()
    mock_session = MagicMock()
    mock_input1 = MagicMock()
    mock_input1.name = "input_ids"
    mock_input2 = MagicMock()
    mock_input2.name = "attention_mask"
    mock_session.get_inputs.return_value = [mock_input1, mock_input2]
    mock_session.run.return_value = [[[0.5]]]

    mock_tokenizer = MagicMock()
    enc = MagicMock()
    enc.ids = [1, 2, 3]
    enc.attention_mask = [1, 1, 1]
    enc.type_ids = [0, 0, 0]
    mock_tokenizer.encode.return_value = enc

    reranker._session = mock_session
    reranker._tokenizer = mock_tokenizer

    scores = reranker.rerank("test query", ["test doc"])
    assert len(scores) == 1

    args = mock_session.run.call_args[0]
    input_feed = args[1]
    assert "input_ids" in input_feed
    assert "attention_mask" in input_feed
    assert "token_type_ids" not in input_feed


def test_bge_reranker_includes_token_type_ids_when_model_accepts_it():
    from unittest.mock import MagicMock

    from power_framework.core.reranker import BGEM3Reranker

    reranker = BGEM3Reranker()
    mock_session = MagicMock()
    mock_input1 = MagicMock()
    mock_input1.name = "input_ids"
    mock_input2 = MagicMock()
    mock_input2.name = "attention_mask"
    mock_input3 = MagicMock()
    mock_input3.name = "token_type_ids"
    mock_session.get_inputs.return_value = [mock_input1, mock_input2, mock_input3]
    mock_session.run.return_value = [[[0.5]]]

    mock_tokenizer = MagicMock()
    enc = MagicMock()
    enc.ids = [1, 2, 3]
    enc.attention_mask = [1, 1, 1]
    enc.type_ids = [0, 0, 0]
    mock_tokenizer.encode.return_value = enc

    reranker._session = mock_session
    reranker._tokenizer = mock_tokenizer

    scores = reranker.rerank("test query", ["test doc"])
    assert len(scores) == 1

    args, _ = mock_session.run.call_args
    input_feed = args[1]
    assert "input_ids" in input_feed
    assert "attention_mask" in input_feed
    assert "token_type_ids" in input_feed

"""Tests for the RerankerManager class."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from huggingface_hub import try_to_load_from_cache

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

    def test_qwen3_reranker_import_error(self):
        import sys
        from unittest.mock import patch

        import pytest

        from power_framework.core.reranker import RerankerManager

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
            with pytest.raises(ImportError, match="qwen3-embed is required"):
                mgr._lazy_init()

    def test_fastembed_reranker_import_error(self):
        import sys
        from unittest.mock import patch

        import pytest

        from power_framework.core.reranker import (
            ALLOW_NONCOMMERCIAL_MODELS_ENV,
            RerankerManager,
        )

        with (
            patch.dict(
                "os.environ",
                {ALLOW_NONCOMMERCIAL_MODELS_ENV: "1", "POWER_RERANKER": "jina"},
            ),
            patch.dict(sys.modules, {"fastembed.rerank.cross_encoder": None}),
        ):
            mgr = RerankerManager()
            with pytest.raises(ImportError, match="fastembed is required"):
                mgr._lazy_init()

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

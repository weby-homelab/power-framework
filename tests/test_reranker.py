"""Tests for the RerankerManager class."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from power_framework.core.reranker import (
    ALLOW_NONCOMMERCIAL_MODELS_ENV,
    NonCommercialModelDisabledError,
    RerankerManager,
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

        from power_framework.core.colbert_reranker import _available_ram_gb, is_colbert_enabled

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

        with patch.dict("os.environ", {"POWER_RERANKER": ""}), pytest.raises(
            ColBERTUnavailableError, match="opt-in"
        ):
            ColBERTLateInteractionReranker()

        with (
            patch.dict("os.environ", {"POWER_RERANKER": "colbert"}),
            patch("power_framework.core.colbert_reranker._available_ram_gb", return_value=1.0),
            pytest.raises(ColBERTUnavailableError, match="requires >="),
        ):
            ColBERTLateInteractionReranker()

        with (
            patch.dict("os.environ", {"POWER_RERANKER": "colbert"}),
            patch("power_framework.core.colbert_reranker._available_ram_gb", return_value=16.0),
        ):
            colbert = ColBERTLateInteractionReranker()
            assert colbert.model_name is not None

    def test_lazy_init_already_initialized(self):
        manager = RerankerManager()
        mock_model = MagicMock()
        manager._model = mock_model
        manager._lazy_init()

    def test_get_reranker_fallback(self):
        from unittest.mock import patch

        from power_framework.core.reranker import RerankerManager, get_reranker

        with patch("power_framework.core.colbert_reranker.is_colbert_enabled", return_value=False):
            r = get_reranker()
            assert isinstance(r, RerankerManager)

        with (
            patch("power_framework.core.colbert_reranker.is_colbert_enabled", return_value=True),
            patch("power_framework.core.colbert_reranker._available_ram_gb", return_value=1.0),
        ):
            r = get_reranker()
            assert isinstance(r, RerankerManager)

    def test_qwen3_reranker_import_error(self):
        import sys
        from unittest.mock import patch

        import pytest

        from power_framework.core.reranker import RerankerManager

        with (
            patch.dict("os.environ", {"POWER_EMBED_PROVIDER": "qwen3"}),
            patch.dict(sys.modules, {"qwen3_embed": None}),
        ):
            mgr = RerankerManager()
            with pytest.raises(ImportError, match="qwen3-embed is required"):
                mgr._lazy_init()

    def test_fastembed_reranker_import_error(self):
        import sys
        from unittest.mock import patch

        import pytest

        from power_framework.core.reranker import ALLOW_NONCOMMERCIAL_MODELS_ENV, RerankerManager

        with (
            patch.dict("os.environ", {ALLOW_NONCOMMERCIAL_MODELS_ENV: "1"}),
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
            patch("power_framework.core.colbert_reranker._available_ram_gb", return_value=16.0),
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








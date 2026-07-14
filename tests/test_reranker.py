"""Tests for the RerankerManager class."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from power_framework.core.reranker import RerankerManager


class TestRerankerManager:
    """Tests for RerankerManager."""

    def test_rerank_returns_scores(self):
        manager = RerankerManager()
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.9, 0.3, 0.7]
        manager._model = mock_model

        scores = manager.rerank("test query", ["doc1", "doc2", "doc3"])
        assert len(scores) == 3
        assert scores == [0.9, 0.3, 0.7]

    def test_rerank_orders_by_relevance(self):
        manager = RerankerManager()
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.3, 0.9, 0.7]
        manager._model = mock_model

        scores = manager.rerank("test query", ["doc1", "doc2", "doc3"])
        assert scores[1] > scores[0]
        assert scores[1] > scores[2]

    def test_rerank_single_document(self):
        manager = RerankerManager()
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.85]
        manager._model = mock_model

        scores = manager.rerank("test query", ["single doc"])
        assert len(scores) == 1
        assert scores[0] == 0.85

    def test_rerank_empty_documents(self):
        manager = RerankerManager()
        mock_model = MagicMock()
        mock_model.predict.return_value = []
        manager._model = mock_model

        scores = manager.rerank("test query", [])
        assert scores == []

    def test_lazy_init_does_not_load_on_construction(self):
        manager = RerankerManager()
        assert manager._model is None

    def test_rerank_calls_predict_with_pairs(self):
        manager = RerankerManager()
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.5, 0.8]
        manager._model = mock_model

        manager.rerank("query", ["doc a", "doc b"])
        mock_model.predict.assert_called_once_with(
            [("query", "doc a"), ("query", "doc b")]
        )

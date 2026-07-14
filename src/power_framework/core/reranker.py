from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastembed.rerank.cross_encoder import TextCrossEncoder

logger = logging.getLogger(__name__)

DEFAULT_RERANKER_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


class RerankerManager:
    def __init__(self, model_name: str = DEFAULT_RERANKER_MODEL) -> None:
        self.model_name = model_name
        self._model: TextCrossEncoder | None = None

    def _lazy_init(self) -> None:
        if self._model is not None:
            return
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
        except ImportError:
            raise ImportError(
                "fastembed is required. Install it with: pip install fastembed"
            ) from None
        self._model = TextCrossEncoder(model_name=self.model_name)

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        self._lazy_init()
        assert self._model is not None
        pairs = [(query, doc) for doc in documents]
        return list(self._model.predict(pairs))

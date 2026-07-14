from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384


class EmbeddingManager:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model: TextEmbedding | None = None

    def _lazy_init(self) -> None:
        if self._model is not None:
            return
        try:
            from fastembed import TextEmbedding
        except ImportError:
            raise ImportError(
                "fastembed is required. Install it with: pip install fastembed"
            ) from None
        logger.info("Loading embedding model %s ...", self.model_name)
        self._model = TextEmbedding(model_name=self.model_name)

    def embed(self, text: str) -> list[float]:
        self._lazy_init()
        assert self._model is not None
        return [float(v) for v in next(self._model.embed([text]))]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._lazy_init()
        assert self._model is not None
        return [[float(v) for v in vec] for vec in self._model.embed(texts)]

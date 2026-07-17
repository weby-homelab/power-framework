from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastembed.rerank.cross_encoder import TextCrossEncoder

logger = logging.getLogger(__name__)

DEFAULT_RERANKER_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"

QWEN3_RERANKER_MODEL = os.getenv(
    "POWER_QWEN3_RERANKER_MODEL", "n24q02m/Qwen3-Reranker-0.6B-ONNX"
)


class RerankerManager:
    def __init__(self, model_name: str = DEFAULT_RERANKER_MODEL) -> None:
        self.model_name = model_name
        self._model: TextCrossEncoder | None = None
        self._use_qwen3 = os.getenv("POWER_EMBED_PROVIDER", "").lower() == "qwen3"

    def _lazy_init(self) -> None:
        if self._model is not None:
            return
        if self._use_qwen3:
            try:
                from qwen3_embed import TextCrossEncoder as Qwen3TextCrossEncoder
            except ImportError:
                raise ImportError(
                    "qwen3-embed is required for Qwen3 reranking. "
                    "Install it with: pip install qwen3-embed"
                ) from None
            self._model = Qwen3TextCrossEncoder(model_name=QWEN3_RERANKER_MODEL)  # type: ignore[assignment]
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
        if self._use_qwen3:
            return [float(s) for s in self._model.rerank(query, documents)]  # type: ignore[attr-defined]
        pairs = [(query, doc) for doc in documents]
        return list(self._model.predict(pairs))  # type: ignore[attr-defined]

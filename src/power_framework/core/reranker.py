from __future__ import annotations

import logging
import os
from typing import Protocol

logger = logging.getLogger(__name__)

DEFAULT_RERANKER_MODEL = "jinaai/jina-reranker-v2-base-multilingual"
ALLOW_NONCOMMERCIAL_MODELS_ENV = "POWER_ALLOW_NONCOMMERCIAL_MODELS"

QWEN3_RERANKER_MODEL = os.getenv("POWER_QWEN3_RERANKER_MODEL", "n24q02m/Qwen3-Reranker-0.6B-ONNX")


class RerankerProtocol(Protocol):
    """Structural type for any reranker backend used by ``get_reranker``."""

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Return a relevance score per document (higher = more relevant)."""
        ...


class NonCommercialModelDisabledError(RuntimeError):
    """Raised when local Jina CC-BY-NC-4.0 use was not explicitly approved."""


class RerankerManager:
    def __init__(self, model_name: str = DEFAULT_RERANKER_MODEL) -> None:
        self.model_name = model_name
        self._model: object | None = None
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
            self._model = Qwen3TextCrossEncoder(model_name=QWEN3_RERANKER_MODEL)
            return
        if os.getenv(ALLOW_NONCOMMERCIAL_MODELS_ENV, "").lower() not in {"1", "true", "yes"}:
            raise NonCommercialModelDisabledError(
                f"{DEFAULT_RERANKER_MODEL} is CC-BY-NC-4.0. Set "
                f"{ALLOW_NONCOMMERCIAL_MODELS_ENV}=1 only for permitted non-commercial use, "
                "or configure a licensed reranker."
            )
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
        scores = self._model.rerank(query, documents)
        return [float(s) for s in scores]


def get_reranker() -> RerankerProtocol:
    """Return the active reranker backend.

    POWER 3.0 Phase 3: ColBERT late-interaction is an opt-in, RAM-gated backend
    (``POWER_RERANKER=colbert``). When unavailable it raises ``ColBERTUnavailableError``
    and the caller must fall back to the canonical Jina v2 cross-encoder.
    """
    from .colbert_reranker import (
        ColBERTLateInteractionReranker,
        ColBERTUnavailableError,
        is_colbert_enabled,
    )

    if is_colbert_enabled():
        try:
            return ColBERTLateInteractionReranker()
        except ColBERTUnavailableError as e:
            logger.warning("ColBERT reranker unavailable (%s); falling back to Jina v2.", e)
    return RerankerManager()

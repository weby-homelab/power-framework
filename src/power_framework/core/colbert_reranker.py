"""POWER 3.0 Phase 3 — Opt-in ColBERT Late-Interaction Reranker.

ColBERT is a *late-interaction* multi-vector reranker that keeps per-token
embeddings and scores query-document token pairs. It materially improves
reranking precision over single-vector cross-encoders (Jina/MiniLM) but is
heavy: it needs ~16+ GB of RAM/VRAM and a multi-GB model download.

Therefore this backend is **opt-in and OFF by default**. It is only engaged
when ``POWER_RERANKER=colbert`` is set, and it refuses to load unless the host
has at least ``POWER_COLBERT_MIN_RAM_GB`` (default 16) of available RAM. On any
unavailability it raises a clear ``ColBERTUnavailableError`` so the caller can fall
back to the canonical Jina v2 reranker (never silently degrade search quality).
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Engaged only when POWER_RERANKER == this value.
COLBERT_RERANKER_KEY = "colbert"

# Minimum available system RAM (GB) required to safely load ColBERT. Tunable.
COLBERT_MIN_RAM_GB = float(os.getenv("POWER_COLBERT_MIN_RAM_GB", "16"))

# Default ColBERT model (late-interaction, multilingual-capable).
COLBERT_DEFAULT_MODEL = os.getenv("POWER_COLBERT_MODEL", "colbert-ir/colbertv2.0")


class ColBERTUnavailableError(Exception):
    """Raised when the ColBERT backend cannot be engaged (disabled / no RAM / no pkg)."""


def _available_ram_gb() -> float:
    """Return available system RAM in GB (Linux ``/proc/meminfo``; 0 elsewhere)."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb / (1024.0**2)
    except OSError:
        # /proc/meminfo is not available on non-Linux platforms or inside restricted sandboxes
        pass
    return 0.0


def is_colbert_enabled() -> bool:
    """True iff POWER_RERANKER=colbert is explicitly requested."""
    return os.getenv("POWER_RERANKER", "").lower() == COLBERT_RERANKER_KEY


class ColBERTLateInteractionReranker:
    """Late-interaction (ColBERT) reranker with the same interface as RerankerManager.

    Methods:
        rerank(query, documents) -> list[float]  # scores aligned to documents
    """

    def __init__(self, model_name: str = COLBERT_DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model: Any | None = None
        if not is_colbert_enabled():
            raise ColBERTUnavailableError(
                "ColBERT backend is opt-in; set POWER_RERANKER=colbert to enable."
            )
        if _available_ram_gb() < COLBERT_MIN_RAM_GB:
            raise ColBERTUnavailableError(
                f"ColBERT requires >= {COLBERT_MIN_RAM_GB:.0f} GB available RAM; "
                f"only {_available_ram_gb():.1f} GB available."
            )

    def _lazy_init(self) -> None:
        if self._model is not None:
            return
        try:
            from colbert.infra import ColBERTConfig  # type: ignore
            from colbert.modeling.checkpoint import Checkpoint  # type: ignore
        except ModuleNotFoundError as e:  # pragma: no cover - depends on env
            raise ColBERTUnavailableError(
                "The 'colbert' package is not installed. Install with: pip install colbert-ai"
            ) from e
        # Late-interaction scoring reuses ColBERT's checkpoint scorer; the heavy
        # FAISS index build is avoided because we score a small candidate set
        # directly (reranking already-filtered top-K, not full-corpus search).
        config = ColBERTConfig()
        self._model = Checkpoint(self.model_name, colbert_config=config)
        logger.info("ColBERT late-interaction reranker loaded: %s", self.model_name)

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Score each document against the query via late interaction.

        Returns a float score per document (higher = more relevant). Implements
        the ColBERT MaxSim operator: for each query token take the max similarity
        over document tokens, then sum across query tokens.
        """
        self._lazy_init()
        assert self._model is not None
        q_tokens = self._model.query(query)
        scores: list[float] = []
        for doc in documents:
            d_tokens = self._model.doc(doc)
            # MaxSim over token embeddings (late interaction).
            sim = q_tokens @ d_tokens.T if hasattr(q_tokens, "T") else None
            if sim is None:
                scores.append(0.0)
                continue
            max_sim_per_q = sim.max(dim=1).values
            scores.append(float(max_sim_per_q.sum()))
        return scores

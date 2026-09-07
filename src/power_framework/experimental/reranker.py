from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
import time
from contextlib import contextmanager
from typing import Protocol

from power_framework.core.egress import EgressOperation
from power_framework.core.model_policy import (
    PreparedModel,
    acquire_model_files,
    force_model_offline,
    prepare_external_model,
)
from power_framework.core.utils import get_cpu_worker_limit
from power_framework.experimental.embeddings import select_onnx_providers, verify_bound_provider

logger = logging.getLogger(__name__)

# Default reranker is now a LICENSE-CLEAN (MIT/Apache) BGE cross-encoder ONNX
# export, NOT the CC-BY-NC-4.0 Jina model. Jina remains reachable only as an
# explicit opt-in under POWER_RERANKER=jina + POWER_ALLOW_NONCOMMERCIAL_MODELS=1.
DEFAULT_RERANKER_MODEL = "onnx-community/bge-reranker-v2-m3-ONNX"
ALLOW_NONCOMMERCIAL_MODELS_ENV = "POWER_ALLOW_NONCOMMERCIAL_MODELS"

# Pinned BGE reranker ONNX export (Apache-2.0 compatible), including SHA-256
# checks for every runtime file (ADR 0001 decision 3).
BGE_RERANKER_ONNX_REPO = os.getenv(
    "POWER_BGE_RERANKER_ONNX_REPO", "onnx-community/bge-reranker-v2-m3-ONNX"
)
BGE_RERANKER_ONNX_REVISION = os.getenv(
    "POWER_BGE_RERANKER_ONNX_REVISION", "6f5ff65298512715a1e669753bc754d2bc8f367b"
)
BGE_RERANKER_PINNED_REPO = "onnx-community/bge-reranker-v2-m3-ONNX"
BGE_RERANKER_PINNED_REVISION = "6f5ff65298512715a1e669753bc754d2bc8f367b"
BGE_RERANKER_FILE_SHA256: dict[str, str] = {
    "model.onnx": "faae32b124a9d54afb7e89b5e9896e03c18a9552d56d1d6b273a709a83012486",
    "model.onnx_data": "f009aa6c6cf21986fd7e0021fa66b20ccce27abc6900a57c7109c8496811bcbe",
    "tokenizer.json": "8bf8afbfd11306bd872018c53bfdf2e160a56f8edbcf49933324404791c148d3",
}

QWEN3_RERANKER_MODEL = os.getenv("POWER_QWEN3_RERANKER_MODEL", "n24q02m/Qwen3-Reranker-0.6B-ONNX")

# Jina remains a documented opt-in only (CC-BY-NC-4.0).
JINA_RERANKER_MODEL = "jinaai/jina-reranker-v2-base-multilingual"
JINA_RERANKER_REVISION = "9cfeff2df7d40d1b78e75e5e9cebec92a99813c9"
_BGE_RERANKER_INIT_LOCK = threading.Lock()


class RerankerProtocol(Protocol):
    """Structural type for any reranker backend used by ``get_reranker``."""

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Return a relevance score per document (higher = more relevant)."""


class NonCommercialModelDisabledError(RuntimeError):
    """Raised when local Jina CC-BY-NC-4.0 use was not explicitly approved."""


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").lower() in {"1", "true", "yes"}


def _verify_sha256(path: str, expected: str) -> None:
    digest = hashlib.sha256()
    with open(path, "rb") as model_file:
        for chunk in iter(lambda: model_file.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        raise RuntimeError(f"model_sha256_mismatch:{os.path.basename(path)}")


@contextmanager
def _prepared_model_constructor_environment(prepared: PreparedModel):
    """Protect a delegated constructor and release staging on any failure."""
    try:
        with force_model_offline():
            yield
    except BaseException:
        prepared.close()
        raise


class RerankerManager:
    """Jina v2 cross-encoder reranker — OPT-IN ONLY (CC-BY-NC-4.0).

    Instantiation fails closed unless BOTH ``POWER_RERANKER=jina`` and
    ``POWER_ALLOW_NONCOMMERCIAL_MODELS=1`` are set. This prevents accidental
    license violations when POWER is used under a GPLv3/commercial context.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name: str = (
            model_name or os.getenv("POWER_JINA_RERANKER_MODEL") or JINA_RERANKER_MODEL
        )
        self._model: object | None = None
        self._prepared_model: PreparedModel | None = None
        self._init_lock = threading.Lock()
        self._use_qwen3 = os.getenv("POWER_EMBED_PROVIDER", "").lower() == "qwen3"

    def _lazy_init(self) -> None:
        if self._model is not None:
            return
        with self._init_lock:
            if self._model is not None:
                return
            self._initialize_model()

    def _initialize_model(self) -> None:
        """Construct a delegated model while the caller holds the init lock."""
        if os.getenv("POWER_RERANKER", "").lower() != "jina" or not _env_flag(
            ALLOW_NONCOMMERCIAL_MODELS_ENV
        ):
            raise NonCommercialModelDisabledError(
                f"{JINA_RERANKER_MODEL} is CC-BY-NC-4.0 and is NOT used by default. "
                f"Set POWER_RERANKER=jina AND POWER_ALLOW_NONCOMMERCIAL_MODELS=1 only for "
                f"permitted non-commercial use, or rely on the MIT/Apache BGE reranker default."
            )
        if self._use_qwen3:
            prepared = prepare_external_model(
                operation=EgressOperation.RERANKING,
                provider="qwen3-reranker-onnx",
                model_reference=os.getenv("POWER_QWEN3_RERANKER_MODEL", QWEN3_RERANKER_MODEL),
            )
            loader_model_name = os.getenv(
                "POWER_QWEN3_RERANKER_MODEL", QWEN3_RERANKER_MODEL
            ).rsplit("@", 1)[0]
            try:
                with force_model_offline():
                    try:
                        from qwen3_embed import TextCrossEncoder as Qwen3TextCrossEncoder
                    except ImportError as e:
                        raise ImportError(
                            "qwen3-embed is required for Qwen3 reranking. "
                            "Install it with: pip install qwen3-embed"
                        ) from e
                    model = Qwen3TextCrossEncoder(
                        model_name=loader_model_name,
                        specific_model_path=prepared.local_reference,
                        threads=get_cpu_worker_limit(),
                        local_files_only=True,
                        lazy_load=False,
                    )
            except BaseException:
                prepared.close()
                raise
            self._model = model
            self._prepared_model = prepared
            return
        model_reference = self.model_name
        if "@" not in model_reference:
            model_reference = f"{model_reference}@{JINA_RERANKER_REVISION}"
        prepared = prepare_external_model(
            operation=EgressOperation.RERANKING,
            provider="jina-reranker",
            model_reference=model_reference,
            expected_license="CC-BY-NC-4.0",
        )
        loader_model_name = model_reference.rsplit("@", 1)[0]
        with _prepared_model_constructor_environment(prepared):
            try:
                from fastembed.rerank.cross_encoder import TextCrossEncoder
            except Exception as e:
                raise ImportError(
                    "fastembed is required. Install it with: pip install fastembed"
                ) from e
            model = TextCrossEncoder(
                model_name=loader_model_name,
                specific_model_path=prepared.local_reference,
                lazy_load=False,
            )
        self._model = model
        self._prepared_model = prepared

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        self._lazy_init()
        assert self._model is not None
        scores = self._model.rerank(query, documents)
        return [float(s) for s in scores]

    def close(self) -> None:
        """Close the delegated loader and release its owned staging tree."""
        model = self._model
        prepared = self._prepared_model
        self._model = None
        self._prepared_model = None
        try:
            close = getattr(model, "close", None) if model is not None else None
            if callable(close):
                close()
        finally:
            if prepared is not None:
                prepared.close()


class BGEM3Reranker:
    """POWER 3.2 canonical reranker: BAAI/bge-reranker-v2-m3 via ONNX Runtime.

    License-clean (MIT/Apache compatible) cross-encoder with full UA↔EN support,
    loaded through ``huggingface_hub`` + direct ``onnxruntime`` (no PyTorch).
    Mirrors ``BGEM3OnnxManager``: pinned revision, optional SHA-256 verification,
    eager probe so retrieval fails loudly rather than silently degrading.
    """

    _MAX_TOKENS = int(os.getenv("POWER_BGE_RERANKER_MAX_TOKENS", "512"))
    _BATCH_SIZE = int(os.getenv("POWER_RERANKER_BATCH_SIZE", "8"))

    def __init__(
        self,
        repo: str | None = None,
        revision: str | None = None,
    ) -> None:
        self.repo: str = (
            repo or os.getenv("POWER_BGE_RERANKER_ONNX_REPO") or BGE_RERANKER_PINNED_REPO
        )
        self.revision: str = (
            revision
            or os.getenv("POWER_BGE_RERANKER_ONNX_REVISION")
            or BGE_RERANKER_PINNED_REVISION
        )
        self.model_name = f"{self.repo}@{self.revision}"
        self._session: object | None = None
        self._tokenizer: object | None = None
        self.active_provider: str | None = None

    def _lazy_init(self) -> None:
        if self._session is not None:
            return
        with _BGE_RERANKER_INIT_LOCK:
            if self._session is not None:
                return
            model_files = acquire_model_files(
                operation=EgressOperation.RERANKING,
                repo=self.repo,
                revision=self.revision,
                provider="bge-reranker-v2-m3-onnx",
                required_files=("onnx/model.onnx", "onnx/model.onnx_data", "tokenizer.json"),
                canonical_repo=BGE_RERANKER_PINNED_REPO,
                canonical_revision=BGE_RERANKER_PINNED_REVISION,
                canonical_provider="bge-reranker-v2-m3-onnx",
                canonical_license="Apache-2.0",
                canonical_hashes={
                    "onnx/model.onnx": BGE_RERANKER_FILE_SHA256["model.onnx"],
                    "onnx/model.onnx_data": BGE_RERANKER_FILE_SHA256["model.onnx_data"],
                    "tokenizer.json": BGE_RERANKER_FILE_SHA256["tokenizer.json"],
                },
                custom_license="Apache-2.0",
            )
            try:
                import onnxruntime as ort
                from tokenizers import Tokenizer
            except ImportError as e:
                raise ImportError(
                    "bge-reranker requires onnxruntime, tokenizers and huggingface-hub. "
                    "Install with: pip install power-framework"
                ) from e

            model_path = model_files["onnx/model.onnx"]
            tok_path = model_files["tokenizer.json"]

            so = ort.SessionOptions()
            so.enable_cpu_mem_arena = False
            so.intra_op_num_threads = get_cpu_worker_limit(
                int(os.getenv("POWER_EMBED_NUM_THREADS", "2"))
                if os.getenv("POWER_EMBED_NUM_THREADS")
                else None
            )
            so.inter_op_num_threads = 1
            providers = select_onnx_providers(ort, env_var="POWER_RERANKER_DEVICE")
            session = ort.InferenceSession(model_path, providers=providers, sess_options=so)
            active_provider = verify_bound_provider(session, providers, "POWER_RERANKER_DEVICE")
            self._session = session
            self.active_provider = active_provider
            try:
                self._tokenizer = Tokenizer.from_file(tok_path)
                self._tokenizer.enable_truncation(max_length=self._MAX_TOKENS)

                # Probe: eagerly verify the backend can allocate and produce a score.
                probe = self._rerank_raw("probe query", "probe passage")
                if probe is None or len(probe) != 1:
                    raise RuntimeError("bge_reranker_onnx_probe_failed")
            except Exception:
                self._session = None
                self._tokenizer = None
                self.active_provider = None
                raise

    def _rerank_batch(self, query: str, documents: list[str]) -> list[float] | None:
        import numpy as np

        assert self._session is not None
        assert self._tokenizer is not None
        if not documents:
            return []

        pairs = [(query, doc) for doc in documents]
        try:
            encodings = self._tokenizer.encode_batch(pairs)
            if not isinstance(encodings, (list, tuple)) or len(encodings) == 0:
                encodings = [self._tokenizer.encode(q, d) for q, d in pairs]
        except Exception:
            encodings = [self._tokenizer.encode(q, d) for q, d in pairs]

        max_len = max(len(enc.ids) for enc in encodings)

        padded_ids = []
        padded_mask = []
        padded_types = []
        pad_id = self._tokenizer.token_to_id("[PAD]") or 0

        for enc in encodings:
            ids = list(enc.ids)
            mask = list(enc.attention_mask)
            types = list(enc.type_ids)
            pad_len = max_len - len(ids)
            if pad_len > 0:
                ids.extend([pad_id] * pad_len)
                mask.extend([0] * pad_len)
                types.extend([0] * pad_len)
            padded_ids.append(ids)
            padded_mask.append(mask)
            padded_types.append(types)

        input_ids = np.array(padded_ids, dtype=np.int64)
        attention_mask = np.array(padded_mask, dtype=np.int64)
        token_type_ids = np.array(padded_types, dtype=np.int64)

        input_feed = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        input_names = {inp.name for inp in self._session.get_inputs()}
        if "token_type_ids" in input_names:
            input_feed["token_type_ids"] = token_type_ids

        logits = self._session.run(None, input_feed)[0]
        scores: list[float] = []
        for i in range(len(documents)):
            val = logits[i]
            while hasattr(val, "__getitem__") and not isinstance(val, (float, int)):
                if not hasattr(val, "__len__") or len(val) == 0:
                    break
                val = val[0]
            raw_val = float(val)
            score = float(1.0 / (1.0 + math.exp(-raw_val)))
            scores.append(score)
        return scores

    def _rerank_raw(self, query: str, document: str) -> list[float] | None:
        return self._rerank_batch(query, [document])

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        self._lazy_init()
        if not documents:
            return []
        batch_size = int(os.getenv("POWER_RERANKER_BATCH_SIZE", "8"))
        if batch_size <= 0:
            batch_size = 8

        scores: list[float] = []
        t0 = time.perf_counter()
        for i in range(0, len(documents), batch_size):
            chunk = documents[i : i + batch_size]
            batch_scores = self._rerank_batch(query, chunk)
            if batch_scores:
                scores.extend(batch_scores)
            else:
                scores.extend([0.0] * len(chunk))
        rerank_ms = (time.perf_counter() - t0) * 1000
        logger.debug(
            "BGEM3Reranker reranked %d docs in %.2f ms (batch_size=%d)",
            len(documents),
            rerank_ms,
            batch_size,
        )
        return scores


class LexicalReranker:
    """License-clean (MIT) local fallback reranker with NO model download.

    Used as the fail-closed fallback when the BGE reranker cannot be loaded
    (e.g. offline host). It ranks documents by lexical/token overlap with the
    query plus a short length prior — never silently falling back to a
    non-commercial model. This guarantees reranked retrieval keeps working
    without leaking into CC-BY-NC-4.0 territory.
    """

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        import re

        q_tokens = set(re.findall(r"[a-z0-9а-яєіїґ']+", query.lower()))  # noqa: RUF001
        scores: list[float] = []
        for doc in documents:
            d_tokens = re.findall(r"[a-z0-9а-яєіїґ']+", doc.lower())  # noqa: RUF001
            if not q_tokens or not d_tokens:
                scores.append(0.0)
                continue
            overlap = sum(1 for t in d_tokens if t in q_tokens)
            precision = overlap / len(d_tokens)
            # Slight prior for shorter, more focused passages.
            length_prior = max(0.0, 1.0 - len(d_tokens) / 2000.0)
            scores.append(round(precision * 0.9 + length_prior * 0.1, 6))
        return scores


def get_reranker() -> RerankerProtocol:
    """Return the active reranker backend.

    POWER 3.2: the canonical default is the MIT/Apache ``BGEM3Reranker``. Jina
    is reachable only as an explicit opt-in (POWER_RERANKER=jina +
    POWER_ALLOW_NONCOMMERCIAL_MODELS=1). ColBERT remains opt-in (POWER_RERANKER=colbert).
    """
    from power_framework.experimental.colbert_reranker import (
        ColBERTLateInteractionReranker,
        ColBERTUnavailableError,
        is_colbert_enabled,
    )

    if is_colbert_enabled():
        try:
            return ColBERTLateInteractionReranker()
        except ColBERTUnavailableError as e:
            logger.warning("ColBERT reranker unavailable (%s); using BGE reranker.", e)

    if os.getenv("POWER_RERANKER", "").lower() == "jina":
        return RerankerManager()

    return BGEM3Reranker()

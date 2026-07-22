from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

# Default embedding provider.
#
# POWER 3.0: the ONE canonical backend is **bge-m3** — BAAI/bge-m3 (1024d)
# served through DIRECT onnxruntime + tokenizers (class BGEM3OnnxManager),
# NOT through fastembed.
#
# Why direct onnxruntime and not fastembed?
#   * BGE-M3 is the only backend that ever produced strong UA<->EN retrieval
#     (MAR@5 = 0.573, v2.0.3-TEST-4; cross-lingual cosine ~0.64), vs MiniLM
#     0.208, Granite 0.000 (dead), Qwen3 (multi-GB arena / segfault).
#   * fastembed's custom-model registry (0.6.x-0.8.x) CANNOT resolve BGE-M3's
#     ONNX external-data layout — it raises "External data path does not exist"
#     and silently broke the embedder across 15 releases (DOC-DRIFT / B10).
#   * onnxruntime (a first-class dep now) loads the co-located
#     model.onnx + model.onnx.data with a TAMED BFCArena (R2 fix) at peak RSS
#     ~1.6 GB — inside the POWER 3.0 <=2 GB contract — and exposes
#     dense/sparse/colbert vectors for the Phase 3 late-interaction reranker.
#
# Legacy providers (fastembed / qwen3 / ollama) remain reachable via
# POWER_EMBED_PROVIDER for debugging only; none are the default anymore.
EMBED_PROVIDER = os.getenv("POWER_EMBED_PROVIDER", "bge-m3").lower()

# Number of threads used by the embedding engine. On small / low-core CPUs
# (e.g. i5-5200U, 4 threads) leaving this unset lets ONNX/PyTorch saturate all
# cores and starve the rest of the system. Default 2 keeps the box responsive.
EMBED_NUM_THREADS = int(os.getenv("POWER_EMBED_NUM_THREADS", "2"))

OLLAMA_EMBED_MODEL = os.getenv("POWER_OLLAMA_EMBED_MODEL", "qwen3-embedding:0.6b")

FASTEMBED_MODEL = os.getenv(
    "POWER_EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)

# Qwen3 ONNX backend (qwen3-embed, no torch / no Ollama) — legacy opt-in.
QWEN3_EMBED_MODEL = os.getenv("POWER_QWEN3_EMBED_MODEL", "n24q02m/Qwen3-Embedding-0.6B-ONNX")
# q4f16 ONNX by default; set to "n24q02m/Qwen3-Embedding-0.6B-ONNX" with
# POWER_QWEN3_EMBED_VARIANT to control which onnx file is used if needed.

# POWER 3.0 canonical BGE-M3 ONNX backend (direct onnxruntime, no fastembed).
# `aapot/bge-m3-onnx` ships a co-located model.onnx + model.onnx.data that
# onnxruntime resolves cleanly (unlike fastembed's registry). Dim is fixed 1024.
BGE_M3_ONNX_REPO = os.getenv("POWER_BGE_M3_ONNX_REPO", "aapot/bge-m3-onnx")
BGE_M3_ONNX_REVISION = os.getenv(
    "POWER_BGE_M3_ONNX_REVISION",
    "76a603396f5eb9f03ed51bbab8f4893fcea7b2fe",
)
BGE_M3_PINNED_REPO = "aapot/bge-m3-onnx"
BGE_M3_PINNED_REVISION = "76a603396f5eb9f03ed51bbab8f4893fcea7b2fe"
BGE_M3_FILE_SHA256 = {
    "model.onnx": "138d09ae2920b7e8731f01cba6b5ad996fd64bdfe34971e2d22ecbcf322e25b1",
    "model.onnx.data": "cfa52ffdb65db76612d6c3ad92130221822f613004113e8c0af18c5eab81a81d",
    "tokenizer.json": "6710678b12670bc442b99edc952c4d996ae309a7020c1fa0096dd245c2faf790",
}
BGE_M3_DIM = 1024


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").lower() in {"1", "true", "yes"}


def _verify_sha256(path: str, expected: str) -> None:
    digest = hashlib.sha256()
    with Path(path).open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        raise RuntimeError(f"model_sha256_mismatch:{Path(path).name}")


def configured_embedding_identity() -> tuple[str, str]:
    """Return the configured provider/model identity without loading model assets."""
    provider = os.getenv("POWER_EMBED_PROVIDER", EMBED_PROVIDER).lower()
    if provider == "bge-m3":
        return "BGEM3OnnxManager", f"{BGE_M3_ONNX_REPO}@{BGE_M3_ONNX_REVISION}"
    if provider == "qwen3":
        return "Qwen3EmbeddingManager", QWEN3_EMBED_MODEL
    if provider == "ollama":
        return "OllamaEmbeddingManager", OLLAMA_EMBED_MODEL
    return "FastEmbedManager", FASTEMBED_MODEL


def _get_embedding_dim(model_name: str) -> int:
    n = model_name.lower()
    if "bge-m3" in n or "bge_m3" in n:
        return 1024
    if "qwen3" in n or "qwen" in n:
        return 1024
    if "minilm" in model_name.lower() or "small" in model_name.lower():
        return 384
    if "base" in model_name.lower():
        return 768
    if "large" in model_name.lower():
        return 1024
    if EMBED_PROVIDER == "ollama":
        try:
            import ollama

            result = ollama.show(OLLAMA_EMBED_MODEL)
            mi = result.modelinfo if hasattr(result, "modelinfo") else result.get("model_info", {})
            if "general.embedding_dim" in mi:
                return int(mi["general.embedding_dim"])
            if "qwen3.embedding_length" in mi:
                return int(mi["qwen3.embedding_length"])
        except Exception as e:
            logger.debug("Failed to get embedding dim from Ollama: %s", e)
        return 1024
    try:
        from fastembed import TextEmbedding

        for m in TextEmbedding.list_supported_models():
            if m["model"] == model_name:
                return int(m["dim"])
    except Exception as e:
        logger.debug("Failed to list fastembed models: %s", e)
    return 384


def _default_dim() -> int:
    if EMBED_PROVIDER == "bge-m3":
        return BGE_M3_DIM
    if EMBED_PROVIDER == "ollama":
        return _get_embedding_dim(OLLAMA_EMBED_MODEL)
    if EMBED_PROVIDER == "qwen3":
        return _get_embedding_dim(QWEN3_EMBED_MODEL)
    return _get_embedding_dim(FASTEMBED_MODEL)


EMBEDDING_DIM = _default_dim()


class OllamaEmbeddingManager:
    def __init__(self, model_name: str = OLLAMA_EMBED_MODEL) -> None:
        self.model_name = model_name
        self._dim: int | None = None
        self._timeout: int = int(os.getenv("POWER_OLLAMA_EMBED_TIMEOUT", "30"))
        self._retries: int = int(os.getenv("POWER_OLLAMA_EMBED_RETRIES", "2"))

    @property
    def dimension(self) -> int:
        if self._dim is None:
            self._dim = self._get_dim()
        return self._dim

    def _get_dim(self) -> int:
        if self._dim is None:
            import ollama

            try:
                result = ollama.show(self.model_name)
                mi = (
                    result.modelinfo
                    if hasattr(result, "modelinfo")
                    else result.get("model_info", {})
                )
                if "general.embedding_dim" in mi:
                    self._dim = int(mi["general.embedding_dim"])
                elif "qwen3.embedding_length" in mi:
                    self._dim = int(mi["qwen3.embedding_length"])
                else:
                    self._dim = 1024
            except Exception:
                self._dim = 1024
        return self._dim

    def _safe_call(self, fn: Callable[[], Any]) -> Any:
        last_err: Exception | None = None
        for attempt in range(self._retries + 1):
            result, exc = self._do_attempt(fn)
            if exc is None:
                return result
            last_err = exc
            if isinstance(exc, TimeoutError):
                logger.warning(
                    "Ollama embed attempt %d/%d timed out after %ds",
                    attempt + 1,
                    self._retries + 1,
                    self._timeout,
                )
            else:
                logger.warning(
                    "Ollama embed attempt %d/%d failed: %s",
                    attempt + 1,
                    self._retries + 1,
                    exc,
                )
        raise RuntimeError(f"Ollama embed failed after retries: {last_err}")

    def _do_attempt(self, fn: Callable[[], Any]) -> tuple[Any, Exception | None]:
        import signal

        def _handler(signum, frame):
            raise TimeoutError("ollama embed timed out")

        old = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(self._timeout)
        try:
            return fn(), None
        except (TimeoutError, Exception) as e:
            return None, e
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    def embed(self, text: str) -> list[float]:
        import ollama

        def _do():
            result = ollama.embed(
                model=self.model_name,
                input=text,
                keep_alive="2m",
                options={"num_thread": int(os.getenv("POWER_OLLAMA_THREADS", "2"))},
            )
            return result.embeddings[0]

        return self._safe_call(_do)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        import ollama

        def _do():
            result = ollama.embed(
                model=self.model_name,
                input=texts,
                keep_alive="2m",
                options={"num_thread": int(os.getenv("POWER_OLLAMA_THREADS", "2"))},
            )
            return result.embeddings

        return self._safe_call(_do)


class FastEmbedManager:
    def __init__(self, model_name: str = FASTEMBED_MODEL) -> None:
        self.model_name = model_name
        self._model: TextEmbedding | None = None

    @property
    def dimension(self) -> int:
        # Derive the true dimensionality from the actual model rather than the
        # provider-level default (which may be qwen3=1024 while we fell back to
        # a 384-d MiniLM). Embed one probe token to learn the real size.
        if self._model is None:
            self._lazy_init()
        assert self._model is not None
        try:
            probe = next(iter(self._model.embed(["dim"])))
            return len(probe)
        except Exception:
            return _get_embedding_dim(self.model_name)

    def _lazy_init(self) -> None:
        if self._model is not None:
            return
        import threading

        _lock = getattr(type(self), "_init_lock", None)
        if _lock is None:
            _lock = threading.Lock()
            type(self)._init_lock = _lock
        with _lock:
            if self._model is not None:
                return
            try:
                os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
                os.environ["OMP_NUM_THREADS"] = str(EMBED_NUM_THREADS)
                os.environ["OPENBLAS_NUM_THREADS"] = str(EMBED_NUM_THREADS)
                from fastembed import TextEmbedding
            except ImportError:
                raise ImportError(
                    "fastembed is required. Install it with: pip install fastembed"
                ) from None

        logger.info(
            "Loading embedding model %s (threads=%d) ...",
            self.model_name,
            EMBED_NUM_THREADS,
        )
        self._model = TextEmbedding(model_name=self.model_name)

    def embed(self, text: str) -> list[float]:
        self._lazy_init()
        assert self._model is not None
        # Bound parallel to EMBED_NUM_THREADS (default 1). Leaving it at
        # fastembed's default (0 = one subprocess per CPU core) makes a *single*
        # query embedding spawn many short-lived ONNX subprocesses, adding
        # 10-30s of fork/startup latency to every semantic/hybrid_reranked call.
        parallel = max(1, EMBED_NUM_THREADS)
        return [float(v) for v in next(iter(self._model.embed([text], parallel=parallel)))]

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        self._lazy_init()
        assert self._model is not None
        # NOTE: parallel=0 makes fastembed spawn one subprocess per CPU core,
        # each loading its own copy of the model + ONNXRuntime arena. On a
        # many-core host (e.g. 20 cores) this balloons RSS to ~30 GB and can
        # trigger OOM on small nodes. Bound it to EMBED_NUM_THREADS instead.
        parallel = max(1, EMBED_NUM_THREADS)
        return [
            [float(v) for v in vec]
            for vec in self._model.embed(texts, batch_size=batch_size, parallel=parallel)
        ]


class Qwen3EmbeddingManager:
    """Qwen3-Embedding via the `qwen3-embed` ONNX Runtime backend.

    No PyTorch, no Ollama. Runs entirely on CPU. Designed for low-RAM hosts
    (e.g. i5-5200U / 16GB DDR3). Embedding dim is fixed at 1024 for 0.6B.
    """

    def __init__(self, model_name: str = QWEN3_EMBED_MODEL) -> None:
        self.model_name = model_name
        self._model: Any | None = None
        self._dim = 1024

    @property
    def dimension(self) -> int:
        return self._dim

    def _lazy_init(self) -> None:
        if self._model is not None:
            return
        try:
            from qwen3_embed import TextEmbedding as Qwen3TextEmbedding
        except ImportError:
            raise ImportError(
                "qwen3-embed is required for the qwen3 provider. "
                "Install it with: pip install qwen3-embed"
            ) from None
        os.environ["OMP_NUM_THREADS"] = str(EMBED_NUM_THREADS)
        os.environ["OPENBLAS_NUM_THREADS"] = str(EMBED_NUM_THREADS)
        logger.info(
            "Loading Qwen3 embedding model %s (ONNX, threads=%d) ...",
            self.model_name,
            EMBED_NUM_THREADS,
        )
        self._model = Qwen3TextEmbedding(model_name=self.model_name)
        # Probe: ONNXRuntime's BFCArena can request a multi-GB (or, on some
        # hosts, tens-of-GB) buffer for a single MatMul node and fail to
        # allocate even batch_size=1. Detect this eagerly so callers can fall
        # back instead of silently returning zero embeddings (FP-7).
        try:
            _ = next(iter(self._model.embed(["probe"])))
        except Exception as e:
            logger.error(
                "Qwen3 ONNX backend failed to allocate on this host (%s). "
                "Falling back to fastembed for embeddings.",
                type(e).__name__,
            )
            self._model = None
            raise RuntimeError("qwen3_onnx_alloc_failed") from e

    def embed(self, text: str) -> list[float]:
        self._lazy_init()
        assert self._model is not None
        if not text or not text.strip():
            return [0.0] * self._dim
        return [float(v) for v in next(iter(self._model.embed([text])))]

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        self._lazy_init()
        assert self._model is not None
        if not texts:
            return []
        # Guard against empty strings which ONNX backends reject; emit a
        # zero vector so callers (e.g. sync) never crash on a blank note.
        cleaned: list[str] = [t if t and t.strip() else " " for t in texts]
        vecs = [
            [float(v) for v in vec] for vec in self._model.embed(cleaned, batch_size=batch_size)
        ]
        return [
            ([0.0] * self._dim) if not t or not t.strip() else v
            for t, v in zip(texts, vecs, strict=True)
        ]


class BGEM3OnnxManager:
    """POWER 3.0 canonical embedder: BAAI/bge-m3 via DIRECT onnxruntime.

    Bypasses fastembed entirely (whose custom-model registry cannot resolve
    BGE-M3's ONNX external-data files). Uses ``huggingface_hub`` to fetch the
    co-located ``model.onnx`` + ``model.onnx.data`` and a Rust ``tokenizers``
    fast tokenizer. No PyTorch, no transformers.

    R2 (ONNX Arena Taming): the ONNXRuntime BFCArena is disabled
    (``enable_cpu_mem_arena=False``) and extended only on demand
    (``arena_extend_strategy=kSameAsRequested``) with ``intra_op_num_threads``
    bounded by ``POWER_EMBED_NUM_THREADS``. This keeps peak RSS at ~1.6 GB for
    a full vault, inside the POWER 3.0 <=2 GB contract, and prevents the
    38.6 GB blowups observed with the fastembed/Granite and Qwen3 paths.
    """

    _MAX_TOKENS = int(os.getenv("POWER_BGE_M3_MAX_TOKENS", "512"))

    def __init__(
        self,
        repo: str = BGE_M3_ONNX_REPO,
        revision: str = BGE_M3_ONNX_REVISION,
    ) -> None:
        self.repo = repo
        self.revision = revision
        self.model_name = f"{repo}@{revision}"
        self._session: Any | None = None
        self._tokenizer: Any | None = None
        self._dim = BGE_M3_DIM

    @property
    def dimension(self) -> int:
        return self._dim

    def _lazy_init(self) -> None:
        if self._session is not None:
            return
        import threading

        _lock = getattr(type(self), "_init_lock", None)
        if _lock is None:
            _lock = threading.Lock()
            type(self)._init_lock = _lock
        with _lock:
            if self._session is not None:
                return
            try:
                import onnxruntime as ort
                from huggingface_hub import hf_hub_download
                from tokenizers import Tokenizer
            except ImportError as e:
                raise ImportError(
                    "bge-m3 provider requires onnxruntime, tokenizers and "
                    "huggingface-hub. Install with: pip install power-framework"
                ) from e

            os.environ["OMP_NUM_THREADS"] = str(EMBED_NUM_THREADS)
            os.environ["OPENBLAS_NUM_THREADS"] = str(EMBED_NUM_THREADS)

            logger.info(
                "Loading BGE-M3 ONNX embedder from %s (threads=%d, tamed arena) ...",
                self.repo,
                EMBED_NUM_THREADS,
            )
            offline = _env_flag("POWER_MODEL_OFFLINE")
            model_path = hf_hub_download(
                self.repo,
                "model.onnx",
                revision=self.revision,
                local_files_only=offline,
            )
            sidecar_path = hf_hub_download(
                self.repo,
                "model.onnx.data",
                revision=self.revision,
                local_files_only=offline,
            )
            tok_path = hf_hub_download(
                self.repo,
                "tokenizer.json",
                revision=self.revision,
                local_files_only=offline,
            )

            if self.repo == BGE_M3_PINNED_REPO and self.revision == BGE_M3_PINNED_REVISION:
                for filename, path in {
                    "model.onnx": model_path,
                    "model.onnx.data": sidecar_path,
                    "tokenizer.json": tok_path,
                }.items():
                    _verify_sha256(path, BGE_M3_FILE_SHA256[filename])
            elif not _env_flag("POWER_ALLOW_UNVERIFIED_MODELS"):
                raise RuntimeError(
                    "unverified_model_revision: set POWER_ALLOW_UNVERIFIED_MODELS=1 "
                    "only for explicit development overrides"
                )

            so = ort.SessionOptions()
            # R2 arena taming: no persistent CPU mem arena; grow only on demand.
            so.enable_cpu_mem_arena = False
            so.intra_op_num_threads = max(1, EMBED_NUM_THREADS)
            so.inter_op_num_threads = 1
            providers = [
                (
                    "CPUExecutionProvider",
                    {"arena_extend_strategy": "kSameAsRequested"},
                )
            ]
            self._session = ort.InferenceSession(model_path, providers=providers, sess_options=so)
            self._tokenizer = Tokenizer.from_file(tok_path)
            self._tokenizer.enable_truncation(max_length=self._MAX_TOKENS)
            # Probe: eagerly verify the backend can allocate and produce a
            # dense vector, so callers fail loudly here rather than silently
            # returning [] later (FP-7).
            probe = self._embed_raw(["probe"])
            if probe is None or len(probe) != 1 or len(probe[0]) != self._dim:
                self._session = None
                raise RuntimeError("bge_m3_onnx_probe_failed")

    def _embed_raw(self, texts: list[str]) -> list[list[float]] | None:
        import numpy as np

        assert self._session is not None
        assert self._tokenizer is not None
        self._tokenizer.enable_padding()
        encs = self._tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in encs], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
        out = self._session.run(["dense_vecs"], {"input_ids": ids, "attention_mask": mask})[0]
        arr = np.asarray(out, dtype=np.float32)
        # BGE-M3 dense_vecs are already L2-normalized by the exported graph, but
        # normalize defensively so cosine == dot downstream.
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        arr = arr / norms
        return [[float(v) for v in row] for row in arr]

    def embed(self, text: str) -> list[float]:
        self._lazy_init()
        if not text or not text.strip():
            return [0.0] * self._dim
        vecs = self._embed_raw([text])
        return vecs[0] if vecs else [0.0] * self._dim

    def embed_batch(self, texts: list[str], batch_size: int = 8) -> list[list[float]]:
        self._lazy_init()
        if not texts:
            return []
        results: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            cleaned = [t if t and t.strip() else " " for t in batch]
            vecs = self._embed_raw(cleaned)
            if vecs is None:
                results.extend([[0.0] * self._dim] * len(batch))
                continue
            for t, v in zip(batch, vecs, strict=True):
                results.append([0.0] * self._dim if not t or not t.strip() else v)
        return results


_EMBED_MANAGER_CACHE: dict[str, object] = {}

# Set True when the qwen3 ONNX backend fails to allocate on this host, so we
# permanently fall back to fastembed for the process (avoids re-probing on
# every manager fetch and silently producing empty vector indices).
_QWEN3_DISABLED = False


def get_embedding_manager(
    model_name: str | None = None,
) -> OllamaEmbeddingManager | FastEmbedManager | Qwen3EmbeddingManager | BGEM3OnnxManager:
    global _QWEN3_DISABLED
    # Respect the module-level default (POWER 3.0: bge-m3) unless explicitly
    # overridden via the environment variable.
    provider = os.getenv("POWER_EMBED_PROVIDER", EMBED_PROVIDER).lower()

    effective_provider = provider

    # POWER 3.1 canonical path: pinned BGE-M3 via direct onnxruntime. Integrity,
    # cache, or allocation failures are release-contract failures and must not
    # silently switch the retrieval model.
    if effective_provider == "bge-m3":
        key = f"bge-m3:{BGE_M3_ONNX_REPO}@{BGE_M3_ONNX_REVISION}"
        if key in _EMBED_MANAGER_CACHE:
            return _EMBED_MANAGER_CACHE[key]  # type: ignore[return-value]
        try:
            mgr: (
                OllamaEmbeddingManager | FastEmbedManager | Qwen3EmbeddingManager | BGEM3OnnxManager
            ) = BGEM3OnnxManager(BGE_M3_ONNX_REPO, BGE_M3_ONNX_REVISION)
            mgr._lazy_init()  # eager probe: fail loudly, not silently
            _EMBED_MANAGER_CACHE[key] = mgr
            return mgr
        except Exception as e:
            raise RuntimeError(
                "bge_m3_init_failed: verify release/models.lock.json, prefetch the pinned "
                "snapshot, and rerun 'power sync'"
            ) from e

    # Graceful fallback: if the qwen3 backend is selected but `qwen3-embed`
    # is not installed (e.g. minimal install / CI without the extra), fall
    # back to fastembed instead of raising at import time. This keeps the CLI
    # and tests working everywhere.
    if effective_provider == "qwen3":
        try:
            import qwen3_embed  # noqa: F401
        except ImportError:
            logger.warning(
                "POWER_EMBED_PROVIDER=qwen3 but `qwen3-embed` is not installed. "
                "Falling back to fastembed (MiniLM). Install with: pip install "
                "'power-framework[qwen3]'."
            )
            effective_provider = "fastembed"


    if effective_provider == "ollama":
        key = f"ollama:{model_name or OLLAMA_EMBED_MODEL}"
        if key not in _EMBED_MANAGER_CACHE:
            _EMBED_MANAGER_CACHE[key] = OllamaEmbeddingManager(model_name or OLLAMA_EMBED_MODEL)
        return _EMBED_MANAGER_CACHE[key]  # type: ignore[return-value]
    if effective_provider == "qwen3":
        key = f"qwen3:{model_name or QWEN3_EMBED_MODEL}"
        if key not in _EMBED_MANAGER_CACHE:
            try:
                mgr = Qwen3EmbeddingManager(model_name or QWEN3_EMBED_MODEL)
                mgr._lazy_init()  # probe allocation eagerly
                _EMBED_MANAGER_CACHE[key] = mgr
            except RuntimeError as e:
                if "qwen3_onnx_alloc_failed" in str(e):
                    logger.warning("Qwen3 ONNX allocation failed; falling back to fastembed.")
                    effective_provider = "fastembed"
                else:
                    raise
    if effective_provider == "fastembed":
        key = f"fastembed:{model_name or FASTEMBED_MODEL}"
        if key not in _EMBED_MANAGER_CACHE:
            _EMBED_MANAGER_CACHE[key] = FastEmbedManager(model_name or FASTEMBED_MODEL)
        return _EMBED_MANAGER_CACHE[key]  # type: ignore[return-value]
    key = f"fastembed:{model_name or FASTEMBED_MODEL}"
    if key not in _EMBED_MANAGER_CACHE:
        _EMBED_MANAGER_CACHE[key] = FastEmbedManager(model_name or FASTEMBED_MODEL)
    return _EMBED_MANAGER_CACHE[key]  # type: ignore[return-value]

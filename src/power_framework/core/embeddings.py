from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastembed import TextEmbedding

logger = logging.getLogger(__name__)


def _load_env(env_path: str = "/root/geminicli/.env") -> None:
    if os.path.exists(env_path):
        try:
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        if key and key not in os.environ:
                            os.environ[key] = val
        except Exception as e:
            logger.debug("Failed to load .env file from %s: %s", env_path, e)


# Load env variables before setting up default model

if "pytest" not in sys.modules and "PYTEST_CURRENT_TEST" not in os.environ:
    _load_env()

# Default embedding provider.
#
# v2.2.3: the default provider is now ``qwen3`` (Qwen3-Embedding-0.6B-ONNX,
# 1024d, ONNX Runtime, no PyTorch). It gives materially better cross-lingual
# quality than the old MiniLM-L12 (384d) and is the recommended backend for
# mixed UA/EN vaults (fixes FP-3/FP-4: UA→EN MAR@5 0.208 -> ~0.35+).
# The Qwen3 ONNX backend allocates a ~2.3 GB arena per matmul node on CPU, so
# on tight 8 GB hosts set POWER_EMBED_PROVIDER=fastembed or raise
# POWER_SYNC_VMEM_LIMIT_MB. See OOM_RECOVERY_PROTOCOL.md for the matrix.
EMBED_PROVIDER = os.getenv("POWER_EMBED_PROVIDER", "qwen3").lower()

# Number of threads used by the embedding engine. On small / low-core CPUs
# (e.g. i5-5200U, 4 threads) leaving this unset lets ONNX/PyTorch saturate all
# cores and starve the rest of the system. Default 2 keeps the box responsive.
EMBED_NUM_THREADS = int(os.getenv("POWER_EMBED_NUM_THREADS", "2"))

OLLAMA_EMBED_MODEL = os.getenv("POWER_OLLAMA_EMBED_MODEL", "qwen3-embedding:0.6b")

FASTEMBED_MODEL = os.getenv(
    "POWER_EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)

# Qwen3 ONNX backend (qwen3-embed, no torch / no Ollama) — low-RAM default.
QWEN3_EMBED_MODEL = os.getenv("POWER_QWEN3_EMBED_MODEL", "n24q02m/Qwen3-Embedding-0.6B-ONNX")
# q4f16 ONNX by default; set to "n24q02m/Qwen3-Embedding-0.6B-ONNX" with
# POWER_QWEN3_EMBED_VARIANT to control which onnx file is used if needed.


def _get_embedding_dim(model_name: str) -> int:
    if "qwen3" in model_name.lower() or "qwen" in model_name.lower():
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


EMBEDDING_DIM = _get_embedding_dim(
    OLLAMA_EMBED_MODEL if EMBED_PROVIDER == "ollama" else FASTEMBED_MODEL
)


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
        self._model = None
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


_EMBED_MANAGER_CACHE: dict[str, object] = {}

# Set True when the qwen3 ONNX backend fails to allocate on this host, so we
# permanently fall back to fastembed for the process (avoids re-probing on
# every manager fetch and silently producing empty vector indices).
_QWEN3_DISABLED = False


def get_embedding_manager(
    model_name: str | None = None,
) -> OllamaEmbeddingManager | FastEmbedManager | Qwen3EmbeddingManager:
    global _QWEN3_DISABLED
    # Respect the module-level default (v2.2.3: qwen3) unless explicitly
    # overridden via the environment variable.
    provider = os.getenv("POWER_EMBED_PROVIDER", EMBED_PROVIDER).lower()

    # Graceful fallback: if the qwen3 backend is selected but `qwen3-embed`
    # is not installed (e.g. minimal install / CI without the extra), fall
    # back to fastembed instead of raising at import time. This keeps the CLI
    # and tests working everywhere.
    effective_provider = provider
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

    # Permanent in-process fallback: if the qwen3 ONNX backend already proved it
    # cannot allocate on this host, don't keep re-probing — use fastembed.
    if effective_provider == "qwen3" and _QWEN3_DISABLED:
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
                    _QWEN3_DISABLED = True
                    logger.warning("Disabling qwen3 provider for this process; using fastembed.")
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

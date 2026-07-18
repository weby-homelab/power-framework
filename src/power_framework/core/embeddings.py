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

# Default embedding provider (v2.2.0 low-RAM work).
#
# We default to ``fastembed`` with the multilingual MiniLM-L12 model. It is a
# small ONNX model (~470 MB weights + tiny runtime) that, with the batched
# sync path added in v2.2.0, stays well under 8 GB peak RSS. The ``qwen3``
# ONNX backend (Qwen3-Embedding-0.6B) gives better cross-lingual quality but
# allocates a ~2.3 GB ONNXRuntime arena per matmul node on CPU, so it needs
# >=12 GB and is opt-in via POWER_EMBED_PROVIDER=qwen3. See
# OOM_RECOVERY_PROTOCOL.md for the matrix.
EMBED_PROVIDER = os.getenv("POWER_EMBED_PROVIDER", "fastembed").lower()

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
    if model_name == "BAAI/bge-m3":
        return 1024
    if os.getenv("POWER_EMBED_PROVIDER", "fastembed").lower() == "qwen3":
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
                from fastembed.common.model_description import (
                    ModelSource,
                    PoolingType,
                )
            except ImportError:
                raise ImportError(
                    "fastembed is required. Install it with: pip install fastembed"
                ) from None

        if self.model_name == "BAAI/bge-m3":
            try:
                TextEmbedding.add_custom_model(
                    model="BAAI/bge-m3",
                    pooling=PoolingType.CLS,
                    normalization=True,
                    sources=ModelSource(hf="onnx-community/bge-m3-ONNX"),
                    dim=1024,
                    model_file="onnx/model.onnx",
                    additional_files=["onnx/model.onnx_data"],
                )
            except ValueError:
                # Custom model already registered; safe to ignore.
                pass
            except Exception as e:
                logger.warning("Could not register custom model BAAI/bge-m3: %s", e)

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

    def embed(self, text: str) -> list[float]:
        self._lazy_init()
        assert self._model is not None
        return [float(v) for v in next(iter(self._model.embed([text])))]

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        self._lazy_init()
        assert self._model is not None
        return [[float(v) for v in vec] for vec in self._model.embed(texts, batch_size=batch_size)]


_EMBED_MANAGER_CACHE: dict[str, object] = {}


def get_embedding_manager(
    model_name: str | None = None,
) -> OllamaEmbeddingManager | FastEmbedManager | Qwen3EmbeddingManager:
    # Respect the module-level default (v2.2.0: qwen3) unless explicitly
    # overridden via the environment variable.
    provider = os.getenv("POWER_EMBED_PROVIDER", EMBED_PROVIDER).lower()
    if provider == "ollama":
        key = f"ollama:{model_name or OLLAMA_EMBED_MODEL}"
        if key not in _EMBED_MANAGER_CACHE:
            _EMBED_MANAGER_CACHE[key] = OllamaEmbeddingManager(model_name or OLLAMA_EMBED_MODEL)
        return _EMBED_MANAGER_CACHE[key]  # type: ignore[return-value]
    if provider == "qwen3":
        key = f"qwen3:{model_name or QWEN3_EMBED_MODEL}"
        if key not in _EMBED_MANAGER_CACHE:
            _EMBED_MANAGER_CACHE[key] = Qwen3EmbeddingManager(model_name or QWEN3_EMBED_MODEL)
        return _EMBED_MANAGER_CACHE[key]  # type: ignore[return-value]
    key = f"fastembed:{model_name or FASTEMBED_MODEL}"
    if key not in _EMBED_MANAGER_CACHE:
        _EMBED_MANAGER_CACHE[key] = FastEmbedManager(model_name or FASTEMBED_MODEL)
    return _EMBED_MANAGER_CACHE[key]  # type: ignore[return-value]

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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

DEFAULT_MODEL = os.getenv(
    "POWER_EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)


def _get_embedding_dim(model_name: str) -> int:
    if model_name == "BAAI/bge-m3":
        return 1024
    if "minilm" in model_name.lower() or "small" in model_name.lower():
        return 384
    if "base" in model_name.lower():
        return 768
    if "large" in model_name.lower():
        return 1024
    try:
        from fastembed import TextEmbedding

        for m in TextEmbedding.list_supported_models():
            if m["model"] == model_name:
                return m["dim"]
    except Exception as e:
        logger.debug("Failed to list fastembed models: %s", e)
    return 384


EMBEDDING_DIM = _get_embedding_dim(DEFAULT_MODEL)


class EmbeddingManager:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model: TextEmbedding | None = None

    def _lazy_init(self) -> None:
        if self._model is not None:
            return
        try:
            # Disable symlinks for HF downloads to prevent ONNX Runtime directory escape errors
            os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

            from fastembed import TextEmbedding
            from fastembed.common.model_description import ModelSource, PoolingType
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
                # Already registered
                pass
            except Exception as e:
                logger.warning("Could not register custom model BAAI/bge-m3: %s", e)

        logger.info("Loading embedding model %s ...", self.model_name)
        self._model = TextEmbedding(model_name=self.model_name)

    def embed(self, text: str) -> list[float]:
        self._lazy_init()
        assert self._model is not None
        return [float(v) for v in next(iter(self._model.embed([text])))]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._lazy_init()
        assert self._model is not None
        return [[float(v) for v in vec] for vec in self._model.embed(texts)]

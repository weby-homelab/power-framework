from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024


class EmbeddingManager:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model: TextEmbedding | None = None

    def _lazy_init(self) -> None:
        if self._model is not None:
            return
        try:
            import os

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

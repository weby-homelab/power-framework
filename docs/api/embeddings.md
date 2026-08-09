# Embeddings

## `get_embedding_manager`

Factory that returns the configured dense embedding manager. The POWER 3.0
canonical backend is **`BAAI/bge-m3`** (1024d), served through **direct ONNX
Runtime + `tokenizers`** (`BGEM3OnnxManager`) — deliberately NOT through
`fastembed`, whose custom-model registry cannot resolve BGE-M3's ONNX
external-data files.

```python
get_embedding_manager(provider: str | None = None) -> (
    OllamaEmbeddingManager
    | FastEmbedManager
    | Qwen3EmbeddingManager
    | BGEM3OnnxManager
)
```

- `provider`: overrides `POWER_EMBED_PROVIDER`. One of `bge-m3` (default),
  `fastembed`, `qwen3`, `ollama`. Legacy providers are opt-in for debugging only.

### ONNX device/provider contract

The canonical ONNX managers select the device from `POWER_EMBED_DEVICE`; the
reranker uses `POWER_RERANKER_DEVICE` and falls back to the embedding setting
when it is unset. Supported values are `auto`, `cpu`, `cuda`, `rocm`, and
`directml`.

- `auto` may bind `CPUExecutionProvider`, but logs the provider actually bound
  by the created `InferenceSession`.
- An explicit GPU device fails closed when the session binds CPU or a different
  provider. It never silently turns a requested GPU run into a CPU benchmark.
- Before provider probing, POWER calls the optional
  `onnxruntime.preload_dlls()` hook used by pip-installed CUDA/cuDNN wheels.
- Provider names are resolved case-insensitively because ONNX Runtime builds
  differ in the spelling of the ROCm provider.
- `BGEM3OnnxManager.active_provider` and `BGEM3Reranker.active_provider` hold
  the verified provider after successful session creation; a failed check does
  not retain the invalid session.

`POWER_EMBED_DEVICE=cuda` and `POWER_RERANKER_DEVICE=cuda` are therefore
runtime assertions, not performance hints. Set the corresponding variable to
`auto` when CPU fallback is intended.

### Canonical — `BGEM3OnnxManager`

```python
BGEM3OnnxManager(model_name: str = "BAAI/bge-m3")
```

- Direct `onnxruntime` + `tokenizers` loader (no PyTorch, no fastembed).
- Fixed **1024-d** vectors; peak RSS ≈ 1.6 GB — inside the POWER 3.0 ≤2 GB contract.
- Strong UA↔EN retrieval (vector MAR@5 ≈ 0.573, cross-lingual cosine ≈ 0.771 UA→EN).

### Legacy opt-in managers

| Manager                  | Backend                         | Dim    | Notes                              |
| ------------------------ | ------------------------------- | ------ | ---------------------------------- |
| `FastEmbedManager`       | `fastembed` (MiniLM-L12-v2)     | 384    | Lightweight, EN-biased, weak UA↔EN |
| `Qwen3EmbeddingManager`  | `qwen3-embed` (Qwen3-0.6B ONNX) | 1024   | CPU-friendly, no PyTorch           |
| `OllamaEmbeddingManager` | Ollama server                   | varies | Local LLM host required            |

### Methods (all managers)

#### `embed(text: str) -> list[float]`

Generate a dense vector for a single text.

- **Parameters**: `text` (str).
- **Returns**: A list of floats representing the embedding vector.

#### `embed_batch(texts: list[str]) -> list[list[float]]`

Generate dense vectors for a batch of texts (adaptive batch halving on OOM).

- **Parameters**: `texts` (list of strings).
- **Returns**: A list of float lists, each the embedding vector for the corresponding input text.

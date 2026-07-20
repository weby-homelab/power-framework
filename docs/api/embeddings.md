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

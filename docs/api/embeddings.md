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

### Model acquisition security contract

The canonical BGE-M3 loader uses the pinned repository, immutable commit, and
complete runtime-file SHA-256 manifest from `release/models.lock.json`. A
complete cached canonical snapshot works with the default
`POWER_EGRESS_POLICY=deny`; a missing file fails before any HF network call
under deny/offline policy. An explicitly permissive policy may fetch the
missing pinned files through the central egress gate and verifies them before
loading.
`POWER_MODEL_OFFLINE=1`, `HF_HUB_OFFLINE=1`, and `TRANSFORMERS_OFFLINE=1` all
force cache-only behavior, even when a permissive egress policy is configured.
Remote acquisition is restricted to the exact HTTPS `huggingface.co` origin.

Legacy FastEmbed and Qwen model references are not authorization grants. A
delegated custom model must use `org/model@<40-hex-commit>` and require both
`POWER_ALLOW_CUSTOM_MODELS=1` and a `POWER_MODEL_APPROVAL` JSON manifest with
exact `operation`, `provider`, `license`, `repo`, `revision`, and a complete
`files` SHA-256 map. The model policy verifies every approved file and gives
the delegated loader a private staging directory containing only those files.
Unapproved, floating, partial, or mismatched models fail closed. Ollama remains
local-loopback-only.

`POWER_EMBED_DEVICE=cuda` and `POWER_RERANKER_DEVICE=cuda` are therefore
runtime assertions, not performance hints. Set the corresponding variable to
`auto` when CPU fallback is intended.

### Canonical — `BGEM3OnnxManager`

```python
BGEM3OnnxManager(repo: str | None = None, revision: str | None = None)
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

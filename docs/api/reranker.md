# Reranker

Cross-encoder reranking modules and backend factory.

| Function / Class | Returns | Description |
| --- | --- | --- |
| `get_reranker()` | `RerankerProtocol` | Factory function returning the canonical `BGEM3Reranker` (or configured opt-in backend) |
| `BGEM3Reranker` | `BGEM3Reranker` | Canonical default reranker: `BAAI/bge-reranker-v2-m3` via ONNX Runtime (MIT/Apache compatible) |
| `RerankerManager` | `RerankerManager` | Legacy/opt-in non-commercial adapter for `jinaai/jina-reranker-v2-base-multilingual` (CC-BY-NC-4.0) |
| `LexicalReranker` | `LexicalReranker` | Fallback lexical/token-overlap reranker without neural model downloads |

## `get_reranker()`

Factory function returning the active reranker backend implementing `RerankerProtocol`.

```python
get_reranker() -> RerankerProtocol
```

Returns the canonical `BGEM3Reranker` by default. When `POWER_RERANKER=colbert` is configured and available, returns `ColBERTLateInteractionReranker`. When `POWER_RERANKER=jina` is set and permitted, returns `RerankerManager`.

## `BGEM3Reranker`

Canonical cross-encoder reranker using `onnx-community/bge-reranker-v2-m3-ONNX` (pinned revision `6f5ff65298512715a1e669753bc754d2bc8f367b`). Fully license-clean (MIT/Apache compatible) with cross-lingual UA↔EN support, running on ONNX Runtime and `tokenizers` without requiring PyTorch.

### Constructor

```python
BGEM3Reranker(
    repo: str = "onnx-community/bge-reranker-v2-m3-ONNX",
    revision: str = "6f5ff65298512715a1e669753bc754d2bc8f367b",
)
```

- `repo`: Hugging Face repository ID for the exported ONNX model.
- `revision`: Git commit hash or revision for the pinned model assets.

### Methods

#### `rerank(query: str, documents: list[str]) -> list[float]`

Predict relevance scores for document strings against a query in bounded batches (`POWER_RERANKER_BATCH_SIZE`, default 8).

- **Parameters**:
    - `query` (str): Search query.
    - `documents` (list[str]): Candidate document texts to evaluate.
- **Returns**: A list of floats representing normalized relevance scores (probabilities in `[0.0, 1.0]`) for each document.

## `RerankerManager` (Legacy / Opt-in Non-Commercial Adapter)

Cross-encoder adapter for `jinaai/jina-reranker-v2-base-multilingual` or Qwen3 reranker. The Jina model is CC-BY-NC-4.0 and is **not** a production default.

It is loaded only when **both** `POWER_RERANKER=jina` and `POWER_ALLOW_NONCOMMERCIAL_MODELS=1` are explicitly set for permitted non-commercial use, and the central immutable approval/hash contract also passes. Otherwise, lazy model initialization on the first `rerank()` call raises a typed policy error.

### Constructor

```python
RerankerManager(model_name: str = "jinaai/jina-reranker-v2-base-multilingual")
```

- `model_name`: Cross-encoder model name to load when the license policy permits it.

For the Jina/Qwen/ColBERT delegated paths, model loading also requires the
central custom-model contract: an immutable `org/model@<40-hex-commit>`
reference, `POWER_ALLOW_CUSTOM_MODELS=1`, and a `POWER_MODEL_APPROVAL` manifest
binding exact operation/provider/license/repository/revision values to a
complete runtime-file SHA-256 map. Verified files are staged privately before
construction; `POWER_MODEL_OFFLINE=1`, `HF_HUB_OFFLINE=1`, and
`TRANSFORMERS_OFFLINE=1` remain authoritative during import, construction, and
inference. Missing approval or cache data fails before a remote loader call.

### Methods

#### `rerank(query: str, documents: list[str]) -> list[float]`

Predict relevance scores for document strings against a query.

## `LexicalReranker`

License-clean (MIT) fallback reranker with no neural model download. Ranks documents by token overlap and length prior.

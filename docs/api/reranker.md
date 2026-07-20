# Reranker

## `RerankerManager`

Cross-Encoder reranker. The POWER 3.0 canonical model is the multilingual
**`jinaai/jina-reranker-v2-base-multilingual`**, served via `fastembed`'s
`TextCrossEncoder`. It fixes the old MiniLM (`ms-marco-MiniLM-L-6-v2`) reranker,
which degraded mix-lingual quality (MAR@5 −22%, ×8 latency).

### Constructor

```python
RerankerManager(model_name: str = "jinaai/jina-reranker-v2-base-multilingual")
```

- `model_name`: the cross-encoder to load. When `POWER_EMBED_PROVIDER=qwen3`, it
  falls back to `Qwen3-Reranker-0.6B-ONNX`; `fastembed` falls back to
  `ms-marco-MiniLM-L-6-v2`.

### Methods

#### `rerank(query: str, documents: list[str]) -> list[float]`

Predict relevance scores for a list of document strings against a query.

- **Parameters**:
    - `query` (str): The search query.
    - `documents` (list of strings): The documents to evaluate.
- **Returns**: A list of floats representing the predicted relevance score for each document (higher score means more relevant).

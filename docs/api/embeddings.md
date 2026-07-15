# Embeddings

## `EmbeddingManager`

Class for managing local dense vector embeddings using the `fastembed` library. It loads a pre-trained ONNX model for CPU-optimized inference.

### Constructor

```python
EmbeddingManager(model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
```

- `model_name`: The name of the fastembed model to load. Default is `"sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"` (384-dimensional) for lightweight multilingual semantic search. Can be customized via `POWER_EMBEDDING_MODEL` environment variable.

### Methods

#### `embed(text: str) -> list[float]`

Generate a dense vector embedding for a single text string.

- **Parameters**: `text` (str).
- **Returns**: A list of floats representing the embedding vector.

#### `embed_batch(texts: list[str]) -> list[list[float]]`

Generate dense vector embeddings for a list of text strings in batch.

- **Parameters**: `texts` (list of strings).
- **Returns**: A list of float lists, where each list is the embedding vector for the corresponding input text.

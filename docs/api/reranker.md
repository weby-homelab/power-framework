# Reranker

## `RerankerManager`

Class for managing local Cross-Encoder reranking using the `fastembed` library. It loads a pre-trained ONNX model to evaluate query-document relevance scores.

### Constructor

```python
RerankerManager(model_name: str = "Xenova/ms-marco-MiniLM-L-6-v2")
```

- `model_name`: The name of the cross-encoder model to load. Default is `"Xenova/ms-marco-MiniLM-L-6-v2"`.

### Methods

#### `rerank(query: str, documents: list[str]) -> list[float]`

Predict relevance scores for a list of document strings against a query.

- **Parameters**:
  - `query` (str): The search query.
  - `documents` (list of strings): The documents to evaluate.
- **Returns**: A list of floats representing the predicted relevance score for each document (higher score means more relevant).

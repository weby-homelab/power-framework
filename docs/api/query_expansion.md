# Query Expansion

## `QueryExpander`

Class for expanding a search query into multiple variants using a local synonym map and an optional LLM-based fallback.

### Constructor

```python
QueryExpander(use_llm: bool = False, api_key: str | None = None)
```

- `use_llm` (bool): Whether to enable LLM-based query expansion. Default is `False`.
- `api_key` (str | None): Optional OpenRouter API key. If not provided, falls back to the `OPENROUTER_API_KEY` environment variable.

### Attributes

#### `SYNONYM_MAP`

A class-level dictionary containing bidirectional synonym mappings (English & Ukrainian) for key terms (e.g. *deploy* ↔ *розгортання*, *docker* ↔ *container*).

### Methods

#### `expand(query: str) -> list[str]`

Expand the search query into unique variants.

- **Parameters**: `query` (str): The search query.
- **Returns**: A list of unique expanded search queries (always includes the original query).

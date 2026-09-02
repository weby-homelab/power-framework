# Query Expansion

## `QueryExpander`

Class for expanding a search query into multiple variants using a local synonym map and an optional LLM-based fallback.

### Constructor

```python
QueryExpander(
    use_llm: bool = False,
    api_key: str | None = None,
    sensitivity: str = "internal",
)
```

- `use_llm` (bool): Whether to enable LLM-based query expansion. Default is `False`.
- `api_key` (str | None): Optional OpenRouter API key. If not provided, falls back to the `OPENROUTER_API_KEY` environment variable.
- `sensitivity` (str): Egress sensitivity required by the central policy before
  an LLM request. The default is `internal`.

Remote expansion uses the default `https://openrouter.ai/api/v1` origin. A custom
`POWER_LLM_API_BASE` is accepted only when its exact HTTPS origin is listed in
`POWER_LLM_ALLOWED_ORIGINS`; private, loopback, link-local, metadata, malformed,
and redirect-downgraded endpoints are rejected. The bearer token is never sent
to a different redirect origin. `api_base=opencode` is the explicit local CLI
sentinel and does not perform HTTP egress.

### Attributes

#### `SYNONYM_MAP`

A class-level dictionary containing bidirectional synonym mappings (English & Ukrainian) for key terms (e.g. *deploy* ↔ *розгортання*, *docker* ↔ *container*).

### Methods

#### `expand(query: str) -> list[str]`

Expand the search query into unique variants.

- **Parameters**: `query` (str): The search query.
- **Returns**: A list of unique expanded search queries (always includes the original query).

# Architecture

## Package layout

```
src/power_framework/
├── __init__.py         # Public API exports
├── py.typed            # PEP 561 marker
├── core/
│   ├── __init__.py     # Re-exports all core modules
│   ├── cli.py          # CLI entry point (argparse) — 15 commands
│   ├── constants.py    # Centralized constants (exclusion lists, skip files, system dirs)
│   ├── healer.py       # Frontmatter Healer
│   ├── markdown_checks.py  # Markdown quality checks
│   ├── models.py       # OKFMetadata, NoteType, NoteStatus
│   ├── parser.py       # YAML frontmatter parsing (PyYAML)
│   ├── linter.py       # Vault health + ROT audit + archive
│   ├── indexer.py      # Hierarchical index generation
│   ├── relations.py    # Entity extraction + relation suggestions (Graph RAG)
│   ├── rot_scoring.py  # A2 scoring: dedup, freshness, link rot, usage
│   ├── searcher.py     # Full-text search (FTS5/Vector/Hybrid/Reranked)
│   ├── embeddings.py   # Dense embedding managers (BGEM3OnnxManager canonical; fastembed/qwen3/ollama opt-in)
│   ├── reranker.py     # Cross-Encoder reranker (BGE ONNX default; Jina opt-in)
│   ├── query_expansion.py # Synonym map (EN/UK) + OpenRouter Multi-Query expansion
│   ├── chunker.py      # Semantic & contextual chunker (Anthropic Contextual Retrieval)
│   ├── metrics/        # Retrieval metrics (legacy discounted lexical gain; true UDCG deferred)
│   └── utils.py        # Path safety, atomic writes, version, rate limiter
└── mcp/
    ├── __init__.py     # Package marker
    ├── __main__.py     # python -m entry point
    └── power_server.py # FastMCP 3.x server (17 tools + health)

tests/
├── test_cli.py         # CLI functional tests
├── test_healer.py      # Healer unit tests
├── test_indexer.py     # Indexer unit tests
├── test_integration.py # Full-cycle integration tests
├── test_linter.py      # Linter tests
├── test_mcp_server.py  # MCP tool tests
├── test_markdown_checks.py  # Markdown quality tests
├── test_models.py      # Model validation tests
├── test_parser.py      # Parser tests
├── test_relations.py   # Relation suggestions tests
├── test_rot.py         # ROT audit tests
├── test_rot_scoring.py # A2 scoring tests
├── test_searcher.py    # Search scoring tests
└── test_security.py    # Path traversal + atomic write tests
```

## Design decisions

- **`src/` layout** — Standard Python packaging, prevents import confusion
- **FastMCP 3.x (Prefect)** — Modern MCP framework with structured `ToolError`, `ErrorHandlingMiddleware`, `mask_error_details`, async tools, HTTP transport
- **Pydantic v2** — `model_dump()`, strict validation, `field_validator`, UTC-aware timestamps
- **Atomic file writes** — `os.replace()` for crash-safe config persistence
- **Path traversal protection** — `Path.relative_to()` boundary checking (not string-prefix)
- **SSRF hardening** — LinkRotChecker blocks private/loopback/link-local IPs
- **XDG cache dir** — each vault receives a stable UUID in `.power/vault.json`
  and an isolated DB at `~/.cache/power-framework/vaults/<vault-uuid>/search.db`.
  `power sync` builds a complete staged generation, validates source coverage
  and SQLite integrity, then atomically publishes it; a failed stage keeps the
  previous active DB readable.
- **Centralized constants** — `core/constants.py` as single source for all exclusion lists, skip files, system dirs
- **Strict mypy** — All core source modules pass `--strict` type checking
- **Transport flexibility** — stdio (local) or HTTP (Docker) via `POWER_MCP_TRANSPORT` env var

## API boundaries

- **Core library** — All business logic lives in `power_framework.core`. Importable from `power_framework.core` or top-level `power_framework`.
- **CLI** — Thin argparser wrapper delegating to core functions. Entry: `power_framework.core.cli:main`.
- **MCP server** — Thin orchestration layer delegating to core. Uses `asyncio.to_thread()` for all filesystem I/O. Async tools with `ToolError` for structured errors.
- **No circular dependencies** — Core never imports from `mcp`. MCP imports only from core.

## Canonical retrieval registry

`SEARCH_MODE_REGISTRY` in `core/searcher.py` is the executable retrieval
contract. The table below is verified in CI; aliases are intentionally excluded
because they are compatibility input, not canonical modes.

| Mode | Candidate sources | Fusion | Reranker | Requires dense index |
| --- | --- | --- | --- | --- |
| `fts` | `fts` | — | no | no |
| `vector` | `tf_vector` | — | no | no |
| `hybrid` | `fts + tf_vector` | `rrf` | no | no |
| `semantic` | `dense` | — | no | yes |
| `reranked` | `fts + tf_vector + dense` | `rrf` | yes | yes |
| `graph_assisted` | `fts + tf_vector + graph` | `rrf_graph` | no | no |

The current default is `semantic`; `reranked` is an explicit opt-in until the
frozen quality and latency comparison in Issue #187 supports another default.
An unavailable dense index fails closed unless the caller explicitly enables
the documented fallback, which is labelled in the result contract.

## Canonical model contract

- Dense embeddings: `BGEM3OnnxManager`,
  `aapot/bge-m3-onnx@76a603396f5eb9f03ed51bbab8f4893fcea7b2fe`.
- Cross-encoder reranking: `BGEM3Reranker`,
  `onnx-community/bge-reranker-v2-m3-ONNX@6f5ff65298512715a1e669753bc754d2bc8f367b`.
- `jinaai/jina-reranker-v2-base-multilingual` is CC-BY-NC-4.0 and available
  only through the explicit `POWER_RERANKER=jina` plus
  `POWER_ALLOW_NONCOMMERCIAL_MODELS=1` opt-in.

Model revisions and runtime SHA-256 checksums are authoritative in
`release/models.lock.json`. The artifact is code- and environment-scoped; it
does not constitute a performance or quality guarantee.

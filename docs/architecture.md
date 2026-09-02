# Architecture

## Package layout

```
src/power_framework/
├── __init__.py         # Public API exports
├── py.typed            # PEP 561 marker
├── core/
│   ├── __init__.py     # Stable core exports; optional exports are lazy
│   ├── cli.py          # CLI entry point (argparse) — 26 commands
│   ├── constants.py    # Centralized constants (exclusion lists, skip files, system dirs)
│   ├── healer.py       # Frontmatter Healer
│   ├── markdown_checks.py  # Markdown quality checks
│   ├── models.py       # OKFMetadata, NoteType, NoteStatus
│   ├── parser.py       # YAML frontmatter parsing (PyYAML)
│   ├── linter.py       # Vault health + ROT audit + archive
│   ├── indexer.py      # Hierarchical index generation
│   ├── searcher.py     # Full-text search (FTS5/Vector/Hybrid/Reranked)
│   ├── chunker.py      # Semantic & contextual chunker (Anthropic Contextual Retrieval)
│   ├── metrics/        # Retrieval metrics (legacy discounted lexical gain; true UDCG deferred)
│   ├── application.py  # Stable typed use-case boundary for all transports
│   ├── control_plane.py # Content-free Markdown cockpit and optional Bases asset
│   ├── lifecycle.py    # Portable read-only session lifecycle adapters
│   ├── health_loop.py  # Cheap deduplicated health observations/backoff
│   ├── provenance.py   # Opt-in exact-byte evidence capture and verification
│   └── utils.py        # Path safety, atomic writes, version, rate limiter
├── experimental/       # Optional adapters, never imported by core startup
│   ├── embeddings.py    # Dense embedding managers
│   ├── reranker.py      # Cross-encoder and opt-in rerankers
│   ├── query_expansion.py # Synonym/LLM query expansion
│   ├── relations.py     # Graph relation suggestions
│   ├── rot_scoring.py   # Semantic ROT scoring
│   └── graph_extraction.py # Untrusted graph candidates
├── mcp/
    ├── __init__.py     # Package marker
    ├── entrypoint.py   # public power-mcp launcher and preflight
    ├── preflight.py    # dependency-light vault boundary check
    └── power_server.py # official MCP SDK v2 stdio server (20 tools)
└── web/               # optional Web UI adapter shipped in the same wheel
    ├── app.py         # power-web ASGI entry point
    ├── clients/       # ApplicationService adapter
    └── routes/        # authenticated Web UI routes

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
- **Official MCP Python SDK v2** — Modern MCP server/client primitives with
  2026-07-28 protocol interoperability, structured `ToolError`, async tools,
  and stdio transport
- **Pydantic v2** — `model_dump()`, strict validation, `field_validator`, UTC-aware timestamps
- **Atomic file writes** — `os.replace()` for crash-safe config persistence
- **Path traversal protection** — `Path.relative_to()` boundary checking (not string-prefix)
- **SSRF hardening** — external checks resolve all A/AAAA records, reject every
  non-global address, pin direct connections, and revalidate bounded redirects;
  LLM origins require an explicit HTTPS allowlist
- **XDG cache dir** — each vault receives a stable UUID in `.power/vault.json`
  and an isolated DB at `~/.cache/power-framework/vaults/<vault-uuid>/search.db`.
  `power sync` builds a complete staged generation, validates source coverage
  and SQLite integrity, then atomically publishes it; a failed stage keeps the
  previous active DB readable.
- **Centralized constants** — `core/constants.py` as single source for all exclusion lists, skip files, system dirs
- **Strict mypy** — All core source modules pass `--strict` type checking
- **Transport boundary** — native `power-mcp` uses stdio; Docker runs only the
  authenticated `power-web` Web UI on port 8080

## API boundaries

- **Core library** — Stable FTS, parsing, mutation, handoff and application logic lives in `power_framework.core`. Optional dense, graph and ROT adapters live in `power_framework.experimental` and are loaded only when requested.
- **CLI** — Thin argparser wrapper delegating to core functions. Entry: `power_framework.core.cli:main`.
- **MCP server** — Thin orchestration layer delegating to the application
  boundary for stable use cases. Uses `asyncio.to_thread()` for filesystem I/O;
  legacy tools retain compatibility wrappers while new workflows use typed
  envelopes and content-free receipts.
- **Lifecycle and health** — Native hooks are optional; every supported client
  has the portable MCP + Skill contract. Cheap health checks call lightweight
  doctor only, never load a model, use network, or mutate vault content.
- **Optional boundary** — `core.__init__` does not eagerly import embeddings,
  rerankers, graph/relation, query-expansion or ROT implementations. Compatibility
  module paths remain lazy shims while canonical implementations are under
  `power_framework.experimental`.
- **Human cockpit fallback** — `power control-plane` always supports the
  conflict-safe `POWER_STATUS.md` view. `--obsidian-base` adds a marker-owned
  `POWER Control.base` with four optional tables; removing it is scoped to that
  generated file and cannot remove user notes.
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

The current default is `auto`, not `reranked`: it uses a verified dense
generation only when the canonical runtime and local model snapshot are ready;
otherwise it uses FTS and labels the actual mode and fallback reason. Explicit
`semantic` remains fail-closed when its dense contract is unavailable unless the
caller enables the documented, labelled fallback.

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

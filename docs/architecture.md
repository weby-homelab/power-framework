# Architecture

## Package layout

```
src/power_framework/
├── __init__.py         # Public API exports
├── py.typed            # PEP 561 marker
├── core/
│   ├── __init__.py     # Re-exports all core modules
│   ├── cli.py          # CLI entry point (argparse) — 11 commands
│   ├── constants.py    # Centralized constants (v2.0.2)
│   ├── healer.py       # Frontmatter Healer
│   ├── markdown_checks.py  # Markdown quality checks
│   ├── models.py       # OKFMetadata, NoteType, NoteStatus
│   ├── parser.py       # YAML frontmatter parsing (PyYAML)
│   ├── linter.py       # Vault health + ROT audit + archive
│   ├── indexer.py      # Hierarchical index generation
│   ├── relations.py    # Entity extraction + relation suggestions (Graph RAG)
│   ├── rot_scoring.py  # A2 scoring: dedup, freshness, link rot, usage
│   ├── searcher.py     # Full-text search (FTS5/Vector/Hybrid)
│   └── utils.py        # Path safety, atomic writes, version, rate limiter
└── mcp/
    ├── __init__.py     # Package marker
    ├── __main__.py     # python -m entry point
    └── power_server.py # FastMCP 3.x server (12 tools + health)

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
- **XDG cache dir** — `.power_search.db` stored in `~/.cache/power-framework/`, not inside vault
- **Centralized constants** — `core/constants.py` as single source for all exclusion lists, skip files, system dirs
- **Strict mypy** — All 17 source files pass `--strict` type checking
- **Transport flexibility** — stdio (local) or HTTP (Docker) via `POWER_MCP_TRANSPORT` env var

## API boundaries

- **Core library** — All business logic lives in `power_framework.core`. Importable from `power_framework.core` or top-level `power_framework`.
- **CLI** — Thin argparser wrapper delegating to core functions. Entry: `power_framework.core.cli:main`.
- **MCP server** — Thin orchestration layer delegating to core. Uses `asyncio.to_thread()` for all filesystem I/O. Async tools with `ToolError` for structured errors.
- **No circular dependencies** — Core never imports from `mcp`. MCP imports only from core.

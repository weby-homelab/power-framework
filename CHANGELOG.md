# Changelog

All notable changes to the P.O.W.E.R. Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.2] - 2026-07-15

### Fixed
- **Memory OOM Prevention**: Switched default embedding model to `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions) reducing RSS RAM usage from ~6.3 GB to ~680 MB, preventing OOM crashes on low-resource hosts (e.g. 12GB RAM VPS/proxmox nodes).
- **Link Checker Parallelization**: Optimized `LinkRotChecker` using `ThreadPoolExecutor` to check external links in parallel, accelerating extended ROT audit (A2) from minutes to seconds.
- **Configurable Embedding Model**: Added environment variable `POWER_EMBEDDING_MODEL` to customize the model, with support for automatic `.env` loading and test suite isolation.
- **QueryExpander Empty Key Fallback**: Fixed fallback logic in `QueryExpander` to correctly respect explicitly passed empty `api_key=""` strings.

## [2.0.1] - 2026-07-15

### Changed
- **BAAI/bge-m3 default model**: Bumped default embedding model to `BAAI/bge-m3` (1024 dimensions) with custom ONNX community source registration.

## [2.0.0] - 2026-07-14

### Added
- **Dense Embeddings & Hybrid Search**: Integrated `fastembed` (`BAAI/bge-small-en-v1.5`) for local CPU-optimized dense vector embeddings. Added SQLite `chunk_embeddings` storage and `hybrid_reranked` search mode.
- **Cross-Encoder Reranking**: Integrated `RerankerManager` (`Xenova/ms-marco-MiniLM-L-6-v2`) to rank search candidates by query-document relevance scores.
- **Semantic Chunker**: Added `SemanticChunker` implementing the Anthropic Contextual Retrieval pattern, splitting markdown by H2/H3 headers, paragraphs, or fixed size, and prefixing each chunk with parent document context.
- **Query Expansion**: Added local synonym mappings (EN/UA) and LLM-based expansion via OpenRouter in `QueryExpander`.
- **GraphRAG Typed Relations**: Upgraded relation linking in OKF metadata with typed schemas (`path`, `relation`, `confidence`) and added a Mermaid export feature for note-level subgraphs.
- **Semantic ROT & Contradiction Audits**: Enhanced ROT hygiene checks with dense cosine similarity duplicate detection. Added `ContradictionDetector` to identify conflicting metadata or logical contradictions via LLM.
- **FastMCP Lazy Loading Tool Mapping**: Updated MCP tool registration schemas to support fast lazy-loading.
- **API Documentation**: Created comprehensive API markdown documentation for all four new RAG modules.

### Changed
- Bumped version to `2.0.0`
- Configured MyPy to ignore/skip external `numpy` type stubs, resolving incompatibility of PEP 695 syntax on Python 3.10/3.11 runtimes.
- Re-formatted codebase and resolved all Ruff linter and MyPy typecheck issues.

## [1.8.0] - 2026-07-06

### Added
- **FastMCP 3.x migration**: Switched from `mcp.server.fastmcp` to standalone `fastmcp>=3.2` (Prefect) — structured `ToolError` error handling, `ErrorHandlingMiddleware` with `mask_error_details=True`, `asyncio.to_thread` wrappers for heavy tools
- **HTTP transport for Docker**: MCP server supports both stdio (local) and HTTP (`:8000` with `/health` endpoint) via `POWER_MCP_TRANSPORT` env var
- **Docker security hardening**: `cap_drop: [ALL]`, `read_only: true`, `tmpfs /tmp`, HEALTHCHECK now correctly pings HTTP endpoint
- **`.github/dependabot.yml`**: Weekly pip + monthly GitHub Actions updates
- **`constants.py`**: Centralized exclusion lists, skip files, and system constants — single source of truth for all modules
- **Structured error reporting**: MCP tools raise `ToolError` instead of returning `"Error: ..."` strings
- **Centralized `__version__`**: Uses `importlib.metadata.version()` with fallback

### Changed
- **Python 3.14** added to CI matrix; `Dockerfile` base image bumped to `python:3.14-slim`
- **`mypy strict = true`**: Now matches CHANGELOG claims — actual strict mode enabled
- **Dependency groups (PEP 735)**: `[dependency-groups].dev` replaces `[project.optional-dependencies].dev`
- **Dev deps bumped**: `pytest>=8.0`, `pytest-asyncio>=0.24`, `pytest-cov>=6.0`, `ruff>=0.8`, `mypy>=1.13`
- **Async MCP tools**: All 11 MCP tools converted to `async def`; heavy operations use `asyncio.to_thread()`
- **`read_sub_index` split**: Read-only `read_sub_index` no longer writes files; `ensure_sub_index` added for write path
- **Test count unified**: README consistently shows 270+ tests, 81%+ coverage
- **CLI stdout/stderr**: `power search` results go to stdout; logs to stderr

### Fixed
- **Path-traversal**: `validate_vault_path` string-prefix weakness replaced with `Path.relative_to()` check
- **SSRF in LinkRotChecker**: Private/loopback/link-local IPs blocked before HTTP HEAD requests
- **Cache isolation**: `.power_search.db` and `.power_usage.db` moved to XDG cache dir (no longer pollute vault)
- **`install.sh` removed**: Stale script referencing pre-1.5.0 layout deleted; `pip install` from GitHub is the supported path
- **`relations.py` mojibake**: Corrupted UTF-8 stopword `"єї"` → `"є"`
- **Dead code removed**: Unused `candidates` variable in `suggest_related`
- **`mcp/__init__.py` added**: Explicit package marker for `from power_framework.mcp import ...` patterns
- **Docker HEALTHCHECK**: Now works with HTTP transport; container no longer perpetually `unhealthy`
- **`__version__` drift**: Single source via `importlib.metadata`; removed hardcoded string in `utils.py`
- **README OIDC claims**: Removed unsubstantiated "Trusted Publishing" claims; documented GitHub Release install path
- **`--cov-fail-under=70` enforced in CI**: Previously bypassed in GitHub Actions
- **Timestamp timezone normalization**: `OKFMetadata.timestamp` validator ensures UTC-aware datetimes

### Security
- **SSRF hardening**: LinkRotChecker blocks private/loopback/link-local IPs
- **Path-traversal hardening**: `relative_to()` replaces string-prefix check
- **Docker hardening**: `cap_drop: [ALL]`, `read_only: true`
- **mypy strict mode**: All source files pass strict type checking

## [1.7.1] - 2026-07-06

### Added
- **Frontmatter Healer**: `power heal <path>` — auto-fills missing fields with `--no-dry-run` and automatic backup
- **Markdown Quality Checks**: `power markdown-check <path>` — trailing whitespace, list markers, header jumps, code block language
- **MCP tools**: `heal_frontmatter_tool` and `check_markdown_tool`
- **Extended ROT Audit (A2)**: content dedup, link rot checks, freshness scoring, usage tracking

### Changed
- **Test suite expanded**: 198 → 270 tests
- **11 CLI commands** and **11 MCP tools**

## [1.7.0] - 2026-07-06

### Added
- **ROT Audit**, **Auto-Archive**, **Relation Suggestions**, **Cron Maintenance**

## [1.5.1] - 2026-07-03

### Added
- Post-Migration Self-Maintenance, empty folder support in hierarchical index

## [1.5.0] - 2026-07-03

### Added
- `src/` layout migration, `power search` CLI, OIDC Trusted Publishing, CodeQL SAST, GitHub Pages docs, FastMCP migration

## [1.4.0] - 2026-07-02

### Added
- CLI entry point (`power` command), init/lint/index/ingest

## [1.3.0] - 2026-07-02

### Added
- `power_core` package, Pydantic v2 schemas, CI/CD

## [1.2.2] - 2026-07-02

### Fixed
- Initial public release

[2.0.2]: https://github.com/weby-homelab/power-framework/compare/v2.0.1...v2.0.2
[2.0.1]: https://github.com/weby-homelab/power-framework/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/weby-homelab/power-framework/compare/v1.8.0...v2.0.0
[1.8.0]: https://github.com/weby-homelab/power-framework/compare/v1.7.1...v1.8.0
[1.7.1]: https://github.com/weby-homelab/power-framework/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/weby-homelab/power-framework/compare/v1.5.1...v1.7.0
[1.5.1]: https://github.com/weby-homelab/power-framework/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/weby-homelab/power-framework/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/weby-homelab/power-framework/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/weby-homelab/power-framework/compare/v1.2.2...v1.3.0
[1.2.2]: https://github.com/weby-homelab/power-framework/releases/tag/v1.2.2

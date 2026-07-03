# Changelog

All notable changes to the P.O.W.E.R. Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.0] - 2026-07-03

### Added
- **`src/` layout migration**: Project restructured to `src/power_framework/` with proper Python packaging, eliminating import confusion
- **`power search` CLI command**: Full-text vault search with relevance scoring, snippet display, and tag/type matching
- **Comprehensive test suite**: 144 tests total (23 new: CLI functional tests, MCP tool tests, full-cycle integration tests)
- **Codecov threshold**: Enforced minimum 70% coverage via `--cov-fail-under` in pytest configuration
- **CodeQL SAST workflow**: Weekly security scan with `security-and-quality` query suite
- **OIDC Trusted Publishing**: PyPI publishing via OpenID Connect — no API tokens needed, zero-secret release pipeline
- **GitHub Pages docs**: `mkdocs-material` site with `mkdocs.yml`, auto-deployed on every `main` push
- **MkDocs documentation**: Full API reference (models, parser, indexer, linter, searcher, utils), CLI guide, MCP server guide, architecture overview, and contributing guide
- **`.editorconfig`**: Consistent editor settings across all contributors
- **`.pre-commit-config.yaml`**: Pre-commit hooks for ruff linting and formatting
- **`SECURITY.md`**: Vulnerability disclosure policy with GPG-encrypted contact

### Changed
- **MCP server**: Migrated from raw `mcp.server.Server` to **FastMCP** — decorator-based tools, ~60% less boilerplate, auto-input-schema from type hints
- **Package namespace**: All imports changed from `power_core.*` to `power_framework.core.*` and `mcp_servers.*` to `power_framework.mcp.*`
- **Entry point**: CLI entry point updated from `power_core.cli:main` to `power_framework.core.cli:main`
- **CI/CD**: Release workflow now publishes to PyPI via Trusted Publishing (OIDC); docs workflow auto-deploys to GitHub Pages
- **Timestamps**: All `datetime.now()` calls migrated to `datetime.now(timezone.utc)` for DTZ compliance
- **Ruff config**: Added `per-file-ignores` for test files (DTZ001, S101, T20) and CLI (T20)

### Fixed
- **MCP server import**: `scan_folder_notes` and `search_vault` were missing from import block — now explicitly imported
- **MyPy strict compliance**: All 11 source files pass `--strict` with zero errors
- **`note_type` parameter**: MCP `ingest_note` tool now correctly casts `str` to `NoteType` enum (myPy arg-type fix)
- **`__main__.py`**: Removed incorrect `asyncio.run()` wrapping around synchronous FastMCP `run()`
- **Ruff DTZ005/DTZ001**: Timezone-aware `datetime` calls across all modules and tests

### Security
- **CodeQL integration**: Weekly SAST scans via `github/codeql-action` with `security-and-quality` queries
- **Dependabot**: Weekly pip dependency updates + monthly GitHub Actions updates
- **Trusted Publishing**: PyPI releases use OIDC — no secrets, no API tokens, no shared credentials

## [1.4.0] - 2026-07-02

### Added
- **CLI entry point** (`power` command): `init`, `lint`, `index`, `ingest` commands for terminal-based vault management
- **`power init`**: Creates a complete OKF-compliant vault structure with P.A.R.A. folders, templates, index.md, and log.md
- **`power lint`**: Runs health checks for broken links, missing metadata, and orphan notes
- **`power index`**: Rebuilds the catalog index.md from all vault notes
- **`power ingest`**: Creates new notes with validated OKF metadata in the correct P.A.R.A. directory

### Changed
- **README.md**: Complete rewrite — user-first with Quick Start, feature table, and architecture collapsed into `<details>`
- **README.ua.md**: Matching Ukrainian rewrite with same structure
- **Description**: Updated from "Hybrid Knowledge Management Framework" to "AI-native toolkit for Obsidian knowledge bases"
- **Version**: Bumped to 1.4.0

## [1.3.0] - 2026-07-02

### Added
- **power_core package**: Shared library with Pydantic-validated OKF models, safe YAML parser, atomic writes, and path traversal protection
- **Pydantic v2 schemas**: Strict validation for all OKF metadata fields (type, title, description, resource, tags, timestamp)
- **Path Traversal protection**: `validate_vault_path()` ensures vault paths stay within allowed boundaries
- **Atomic writes**: `atomic_write()` prevents corruption from interrupted writes
- **Backup support**: `create_backup()` for safe file modification
- **Comprehensive test suite**: pytest tests covering models, parser, indexer, linter, and security
- **GitHub Actions CI**: Automated testing, linting (ruff), type checking (mypy), and security scanning
- **GitHub Actions Release**: Automated release creation on tag push
- **sync-brain.sh**: Cron-compatible auto-sync script with GPG signing support
- **cleanup_branches.py**: Automated merged branch cleanup via GitHub API
- **CONTRIBUTING.md**: Development setup and workflow documentation

### Changed
- **Refactored architecture**: Extracted shared `power_core/` package to eliminate code duplication between MCP server and scripts
- **YAML parsing**: Replaced manual regex-based parsing with PyYAML for reliable frontmatter handling
- **MCP server**: Now uses `power_core` for all business logic with proper input validation
- **install.sh**: Added prerequisite checks (Python 3.10+, curl), dependency installation, and non-root path support
- **Error handling**: Proper exception types (ValueError, FileNotFoundError) instead of generic messages

### Security
- Path Traversal vulnerability fixed in MCP server `vault_path` parameter
- YAML injection prevention via Pydantic validation and string escaping
- Input validation for all MCP tool parameters
- No secrets in repository (all credentials via environment variables)

## [1.2.2] - 2026-07-02

### Fixed
- Initial public release with basic MCP server and skill scripts

[1.5.0]: https://github.com/weby-homelab/P.O.W.E.R/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/weby-homelab/P.O.W.E.R/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/weby-homelab/P.O.W.E.R/compare/v1.2.2...v1.3.0
[1.2.2]: https://github.com/weby-homelab/P.O.W.E.R/releases/tag/v1.2.2

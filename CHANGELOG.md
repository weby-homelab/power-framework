# Changelog

All notable changes to the P.O.W.E.R. Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.3.0]: https://github.com/weby-homelab/P.O.W.E.R/compare/v1.2.2...v1.3.0
[1.2.2]: https://github.com/weby-homelab/P.O.W.E.R/releases/tag/v1.2.2

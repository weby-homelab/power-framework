# Linter

Health-check functions for vault integrity.

| Function | Returns | Description |
|----------|---------|-------------|
| `run_lint_vault(vault_dir)` | `LintResult` | Check all notes for metadata, links, orphans |
| `run_lint_report(vault_dir)` | `str` | Run lint and return formatted report string |

## `LintResult`

Class container for lint check results.

| Attribute/Method | Type | Description |
|------------------|------|-------------|
| `total_notes` | `int` | Number of scanned markdown notes |
| `untyped_files` | `list[tuple[str, str]]` | List of notes with missing/invalid OKF metadata: `(relative_path, reason)` |
| `broken_links` | `list[tuple[str, str]]` | List of broken internal links: `(relative_path, link_target)` |
| `orphans` | `list[str]` | List of relative paths of notes with no inbound links |
| `has_issues` (property) | `bool` | True if any untyped files, broken links, or orphans are found |
| `format_report(vault_dir)` | `str` | Generate a human-readable lint report |


# Linter

Health-check functions for vault integrity.

| Function | Returns | Description |
|----------|---------|-------------|
| `run_lint_vault(path)` | `LintResult` | Check all notes for metadata, links, orphans |
| `run_lint_report(path)` | `str` | Human-readable lint report |

## `LintResult`

| Attribute | Type | Description |
|-----------|------|-------------|
| `total_notes` | `int` | Number of scanned notes |
| `untyped_notes` | `list[str]` | Notes without OKF type |
| `broken_links` | `list[str]` | `[[wikilinks]]` to non-existent notes |
| `orphans` | `list[str]` | Notes not linked from any other note |

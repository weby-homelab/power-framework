# Markdown Quality Checks

Detects and optionally fixes common markdown quality issues.

| Function | Returns | Description |
|----------|---------|-------------|
| `check_trailing_whitespace(content)` | `list[dict]` | Detect lines with trailing whitespace |
| `check_list_markers(content)` | `list[dict]` | Detect inconsistent list markers (`-` vs `*`) at the same indent level |
| `check_header_jumps(content)` | `list[dict]` | Detect header level jumps (e.g. h1 → h3 without h2) |
| `check_code_block_language(content)` | `list[dict]` | Detect fenced code blocks without language hint |
| `check_all(content)` | `list[dict]` | Run all checks, return combined issues |
| `fix_trailing_whitespace(content)` | `str` | Remove trailing whitespace from all lines |
| `fix_list_markers(content, preferred="-")` | `str` | Standardize list markers to the preferred character |
| `fix_all(content)` | `tuple[str, list[str]]` | Fix all auto-fixable issues. Returns (fixed_content, list_of_changes) |

## Issue format

Each check returns a list of issue dicts:

```python
{
    "line": 42,  # 1-indexed line number
    "type": "trailing-whitespace",  # issue category
    "context": "...",  # truncated context snippet
}
```

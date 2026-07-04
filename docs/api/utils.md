# Utils

Utility functions for path safety, file I/O, and versioning.

| Function | Returns | Description |
|----------|---------|-------------|
| `validate_vault_path(path)` | `Path` | Sanity-check vault path (traversal guard) |
| `resolve_vault_path(vault_path)` | `Path` | Resolve argument → env → cwd fallback |
| `atomic_write(path, content)` | `None` | Crash-safe file write via `.tmp` + `os.replace` |
| `clean_note_name(name)` | `str` | Sanitize note filename |
| `create_backup(source, backup_dir)` | `Path` | Copy file to backup directory |

## Constants

| Name | Value |
|------|-------|
| `__version__` | `"1.5.1"` |
| `VAULT_STRUCTURE` | `dict[str, str]` of P.A.R.A. folders |
| `PARA_FOLDERS` | `list[str]` of folder names |

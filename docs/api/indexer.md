# Indexer

Functions for scanning vault notes and generating hierarchical indexes.

| Function | Returns | Description |
|----------|---------|-------------|
| `scan_vault_notes(path)` | `list[NoteFile]` | Recursively scan all `.md` files |
| `scan_folder_notes(path)` | `dict[str, list[NoteFile]]` | Group notes by P.A.R.A. folder |
| `generate_index_content(notes)` | `str` | Build main `index.md` content |
| `generate_main_index_content(folder_notes, counts)` | `str` | Build navigation table |
| `generate_sub_index_content(folder, notes)` | `str` | Build `_index.md` for one folder |
| `run_generate_hierarchical_index(path)` | `str` | Compile full index + sub-indexes |

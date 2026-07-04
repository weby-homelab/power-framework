# Indexer

Functions for scanning vault notes and generating hierarchical indexes.

| Function | Returns | Description |
|----------|---------|-------------|
| `scan_vault_notes(vault_dir)` | `dict[str, list[tuple[str, str, str]]]` | Scan vault directory for notes with valid OKF metadata, grouped by note type |
| `scan_folder_notes(vault_dir)` | `dict[str, list[dict]]` | Scan vault directory grouping notes by their P.A.R.A. folder |
| `generate_index_content(concepts)` | `str` | Generate the legacy flat index.md content |
| `generate_main_index_content(folder_notes)` | `str` | Generate the root index.md as a navigation map linking to sub-indexes |
| `generate_sub_index_content(folder, notes)` | `str` | Generate a detailed _index.md for a specific P.A.R.A. folder |
| `run_generate_index(vault_dir)` | `str` | Generate flat index.md for the given vault directory |
| `run_generate_sub_index(vault_dir, folder)` | `str` | Generate _index.md for a specific P.A.R.A. folder |
| `run_generate_hierarchical_index(vault_dir)` | `str` | Generate hierarchical index: root index.md + per-folder _index.md files |
| `generate_log_initial(vault_dir, note_count)` | `None` | Generate initial log.md if it doesn't exist |


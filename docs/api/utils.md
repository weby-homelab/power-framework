# Utils

Utility functions for path safety, file I/O, and security.

| Function                                           | Returns      | Description                                                          |
| -------------------------------------------------- | ------------ | -------------------------------------------------------------------- |
| `validate_vault_path(vault_path, allowed_root)`    | `Path`       | Sanity-check vault path (traversal guard)                            |
| `resolve_vault_path(arguments, env_var, fallback)` | `Path`       | Resolve vault path from arguments, environment variable, or fallback |
| `atomic_write(filepath, content, encoding)`        | `None`       | Crash-safe file write via `.tmp` + `os.replace`                      |
| `clean_note_name(filename)`                        | `str`        | Sanitize note filename (remove extension and lowercase)              |
| `create_backup(filepath, backup_dir)`              | `Path\|None` | Copy file to backup directory                                        |
| `get_relative_path(filepath, base_dir)`            | `str`        | Get relative path from base directory                                |
| `is_excluded_dir(dirname)`                         | `bool`       | Check if directory should be excluded from scanning                  |
| `is_excluded_orphan(filename, rel_path)`           | `bool`       | Check if file should be excluded from orphan detection               |

## Constants

| Name                    | Source Module  | Value / Description                                         |
| ----------------------- | -------------- | ----------------------------------------------------------- |
| `__version__`           | `utils.py`     | `"2.0.2"`                                                   |
| `EXCLUDED_DIRS`         | `constants.py` | `frozenset` of directory names excluded from scanning       |
| `EXCLUDED_ORPHAN_FILES` | `constants.py` | `frozenset` of filenames excluded from orphan checks        |
| `PARA_FOLDERS`          | `models.py`    | `tuple` of standard P.A.R.A. category folder names          |
| `SKIP_FILES`            | `constants.py` | `frozenset` of filenames excluded from all scanning         |
| `SYSTEM_SKIP_PARTS`     | `constants.py` | `tuple` of directory parts to skip in markdown check        |
| `VAULT_STRUCTURE`       | `models.py`    | `tuple` of all folders defining a compliant vault structure |

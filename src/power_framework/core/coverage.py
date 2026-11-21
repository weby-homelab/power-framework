"""Read-only index coverage reporting without background worker state."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from pathlib import Path

from .constants import is_catalog_filename
from .generation_index import resolve_active_generation_path
from .ignore import should_skip
from .utils import iter_vault_markdown_files
from .vault_storage import existing_vault_db_path

logger = logging.getLogger(__name__)


def count_vault_notes(root: Path) -> int:
    """Count eligible note paths without opening any database."""
    total = 0
    try:
        for filepath in iter_vault_markdown_files(root):
            if filepath.name in ("index.md", "log.md") or is_catalog_filename(filepath.name):
                continue
            if should_skip(root, filepath.relative_to(root).as_posix()):
                continue
            total += 1
    except OSError:
        logger.debug("Unable to calculate total vault coverage", exc_info=True)
    return total


def get_index_coverage(
    vault_dir: Path, *, allow_search_db_override: bool = True
) -> tuple[int, int]:
    """Return indexed and total notes, preferring the authoritative generation."""
    root = Path(vault_dir).expanduser().resolve()
    total = count_vault_notes(root)
    db_path = resolve_active_generation_path(root) or existing_vault_db_path(
        root, allow_search_db_override=allow_search_db_override
    )
    if db_path is None or not db_path.exists():
        return 0, total
    try:
        uri = f"{db_path.absolute().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=30)) as conn:
            row = conn.execute("SELECT COUNT(*) FROM file_metadata").fetchone()
            return (int(row[0]) if row else 0), total
    except sqlite3.Error:
        logger.debug("Unable to calculate indexed vault coverage", exc_info=True)
        return 0, total

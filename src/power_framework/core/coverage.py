"""Read-only index coverage reporting without background worker state."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from pathlib import Path

from .ignore import should_skip
from .vault_storage import vault_db_path

logger = logging.getLogger(__name__)


def get_index_coverage(vault_dir: Path) -> tuple[int, int]:
    """Return ``(indexed_files, total_files)`` for a vault.

    Coverage is observational only.  Search never starts a worker or changes
    the active vault; callers explicitly run ``power sync`` to materialize an
    index.
    """
    root = Path(vault_dir).expanduser().resolve()
    total = 0
    try:
        for filepath in root.rglob("*.md"):
            if filepath.name in ("index.md", "log.md", "_index.md"):
                continue
            if should_skip(root, filepath.relative_to(root).as_posix()):
                continue
            total += 1
    except OSError:
        logger.debug("Unable to calculate total vault coverage", exc_info=True)

    indexed = 0
    db_path = vault_db_path(root)
    if not db_path.exists():
        return indexed, total
    try:
        with closing(sqlite3.connect(str(db_path), timeout=30)) as conn:
            row = conn.execute("SELECT COUNT(*) FROM file_metadata").fetchone()
            indexed = int(row[0]) if row else 0
    except sqlite3.Error:
        logger.debug("Unable to calculate indexed vault coverage", exc_info=True)

    return indexed, total

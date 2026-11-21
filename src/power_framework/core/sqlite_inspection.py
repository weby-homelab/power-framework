"""Inspect checkpointed SQLite stores without creating coordination files."""

from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def checkpoint_stamp(path: Path) -> tuple[int, ...]:
    path = path.resolve(strict=True)
    for suffix in ("-wal", "-journal"):
        try:
            pending = path.with_name(path.name + suffix).stat().st_size
        except FileNotFoundError:
            continue
        if pending:
            raise sqlite3.OperationalError("inspection requires a checkpointed SQLite store")
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


@contextmanager
def inspect_checkpointed_db(database: Path) -> Iterator[sqlite3.Connection]:
    """Refuse journals and changes rather than read an older snapshot or touch WAL/SHM."""
    path = database.resolve(strict=True)
    before = checkpoint_stamp(path)
    # Immutable mode skips locking and ignores WAL; only trust a stable checkpoint.
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True)) as conn:
        yield conn
        if checkpoint_stamp(path) != before:
            raise sqlite3.OperationalError("SQLite store changed during inspection")

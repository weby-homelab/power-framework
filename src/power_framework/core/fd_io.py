"""Managed file-descriptor helpers enforcing safe symlink rejection and deterministic cleanup."""

from __future__ import annotations

import contextlib
import os
from contextlib import contextmanager
from typing import IO, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@contextmanager
def open_fd_nofollow(
    path: Path,
    mode: str,
    flags: int,
    *,
    mode_bits: int = 0o600,
    encoding: str | None = None,
) -> Iterator[IO[Any]]:
    """Open ``path`` with ``O_NOFOLLOW`` and yield a context-managed stream."""
    effective_flags = flags | getattr(os, "O_NOFOLLOW", 0)
    raw_fd = os.open(path, effective_flags, mode_bits)
    fd: int | None = raw_fd
    try:
        handle: IO[Any] = (
            os.fdopen(raw_fd, mode)
            if encoding is None
            else os.fdopen(raw_fd, mode, encoding=encoding)
        )
        fd = None
    finally:
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)
    with handle:
        yield handle

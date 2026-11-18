"""Idempotent index writing that suppresses timestamp-only disk churn."""

from __future__ import annotations

import contextlib
import os
import stat
from typing import TYPE_CHECKING

from .utils import atomic_write

if TYPE_CHECKING:
    from pathlib import Path


def _normalize_frontmatter_timestamp(text: str) -> list[str]:
    """Split on LF and mask a closed frontmatter ``timestamp:`` value."""
    lines = text.split("\n")
    if len(lines) >= 3 and lines[0] == "---":
        for idx in range(1, len(lines)):
            if lines[idx] == "---":
                for fm_idx in range(1, idx):
                    if lines[fm_idx].startswith("timestamp:") and not lines[fm_idx].endswith("\r"):
                        lines[fm_idx] = "timestamp: <IGNORED>"
                        break
                break
    return lines


def _read_regular_utf8_exact(path: Path) -> str | None:
    """Read a non-symlink regular file as exact LF-untranslated UTF-8, or ``None``."""
    if path.is_symlink():
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = -1
    try:
        fd = os.open(path, flags)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        handle = os.fdopen(fd, "r", encoding="utf-8", newline="")
        fd = -1
        with handle:
            return handle.read()
    except (OSError, UnicodeError):
        return None
    finally:
        if fd >= 0:
            with contextlib.suppress(OSError):
                os.close(fd)


def write_index_if_changed(path: Path, content: str) -> bool:
    """Write *content* atomically only when non-timestamp content differs from disk."""
    existing = _read_regular_utf8_exact(path)
    if existing is not None and _normalize_frontmatter_timestamp(
        existing
    ) == _normalize_frontmatter_timestamp(content):
        return False
    atomic_write(path, content)
    return True

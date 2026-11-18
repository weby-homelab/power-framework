"""Idempotent index writing that suppresses timestamp-only disk churn."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .utils import atomic_write

if TYPE_CHECKING:
    from pathlib import Path


def _normalize_frontmatter_timestamp(text: str) -> list[str]:
    """Replace the frontmatter ``timestamp:`` line with a sentinel for comparison."""
    lines = text.splitlines()
    if len(lines) >= 3 and lines[0] == "---":
        for idx in range(1, len(lines)):
            if lines[idx] == "---":
                break
            if lines[idx].startswith("timestamp:"):
                lines[idx] = "timestamp: <IGNORED>"
                break
    return lines


def write_index_if_changed(path: Path, content: str) -> bool:
    """Write *content* atomically only when non-timestamp content differs from disk."""
    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = None
        if (
            existing is not None
            and existing.endswith("\n") == content.endswith("\n")
            and _normalize_frontmatter_timestamp(existing)
            == _normalize_frontmatter_timestamp(content)
        ):
            return False
    atomic_write(path, content)
    return True

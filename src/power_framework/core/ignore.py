"""
P.O.W.E.R. Vault Ignore + Knowledge-Base Scope Resolution.

Realizes the documented lint behavior:
  * ``OKF`` metadata / broken-link / orphan checks are scoped to the
    knowledge base (PARA folders + ``PROTOCOLS/`` + ``brain/`` + root-level daily logs).
  * Files matched by the ``.powerignore`` file at the vault root (gitignore
    semantics) are skipped entirely — this keeps third-party dependency
    trees, build caches and foreign project repositories (e.g. ``projects/``)
    out of the knowledge-base lint.

This makes the existing ``.powerignore`` file authoritative instead of dead
documentation.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import TYPE_CHECKING

from .constants import EXCLUDED_DIRS, PARA_FOLDERS_

if TYPE_CHECKING:
    from collections.abc import Iterator

POWERIGNORE_NAME = ".powerignore"

# Knowledge-base scope: PARA folders, protocol notes, and nested brain/ vaults.
KB_SCOPE_PREFIXES: frozenset[str] = frozenset(PARA_FOLDERS_) | {"PROTOCOLS", "brain"}

# Root-level daily logs (YYYY-MM-DD_*.md) are part of the knowledge base.
_DAILY_LOG_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_.*\.md$")

_CACHE: dict[str, list[tuple[bool, bool, str, bool]]] = {}


def in_kb_scope(rel_path: str) -> bool:
    """Return True if *rel_path* lives inside the knowledge-base scope."""
    parts = Path(rel_path).parts
    if len(parts) == 1:
        # Root-level file: only daily logs are in scope.
        return bool(_DAILY_LOG_RE.match(parts[0]))
    return parts[0] in KB_SCOPE_PREFIXES


def _parse_powerignore(vault_dir: Path) -> list[tuple[bool, bool, str, bool]]:
    """Parse ``.powerignore`` into a list of (negated, is_dir, pattern, anchored)."""
    path = vault_dir / POWERIGNORE_NAME
    rules: list[tuple[bool, bool, str, bool]] = []
    if not path.exists():
        return rules
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:].strip()
        is_dir = line.endswith("/")
        pat = line[:-1] if is_dir else line
        anchored = "/" in pat
        rules.append((negated, is_dir, pat, anchored))
    return rules


def _get_rules(vault_dir: Path) -> list[tuple[bool, bool, str, bool]]:
    key = str(vault_dir)
    if key not in _CACHE:
        _CACHE[key] = _parse_powerignore(vault_dir)
    return _CACHE[key]


def is_ignored(vault_dir: Path, rel_path: str) -> bool:
    """Return True if *rel_path* matches a ``.powerignore`` rule (last match wins)."""
    rules = _get_rules(vault_dir)
    if not rules:
        return False
    parts = Path(rel_path).parts
    name = parts[-1]
    ignored = False
    for negated, is_dir, pat, anchored in rules:
        hit = False
        if anchored:
            if rel_path == pat or rel_path.startswith(pat + "/"):
                hit = True
        elif is_dir:
            if pat in parts or rel_path == pat or rel_path.startswith(pat + "/"):
                hit = True
        else:
            if fnmatch.fnmatch(name, pat):
                hit = True
        if hit:
            ignored = not negated
    return ignored


def should_skip(vault_dir: Path, rel_path: str) -> bool:
    """Return True if a markdown file should be skipped by vault scanners.

    A file is skipped when it lives in an excluded directory, falls outside
    the knowledge-base scope, or matches a ``.powerignore`` rule.
    """
    parts = Path(rel_path).parts
    if any(part in EXCLUDED_DIRS for part in parts):
        return True
    if not in_kb_scope(rel_path):
        return True
    return bool(is_ignored(vault_dir, rel_path))


def iter_markdown(vault_dir: Path) -> Iterator[tuple[Path, str]]:
    """Yield ``(filepath, rel_path)`` for every in-scope, non-ignored ``.md`` file."""
    for filepath in vault_dir.rglob("*.md"):
        rel_path = str(filepath.relative_to(vault_dir))
        if should_skip(vault_dir, rel_path):
            continue
        yield filepath, rel_path

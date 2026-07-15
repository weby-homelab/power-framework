"""
P.O.W.E.R. Utility Functions.

Path validation, atomic writes, backup management, and security helpers.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import EXCLUDED_DIRS, EXCLUDED_ORPHAN_FILES, PARA_FOLDERS_

try:
    import pathspec

    _HAS_PATHSPEC = True
except ImportError:  # pragma: no cover - pathspec is a declared dependency
    pathspec = None  # type: ignore[assignment]
    _HAS_PATHSPEC = False

# User-configurable ignore file (gitignore syntax) at the vault root.
POWERIGNORE_FILE = ".powerignore"


def validate_vault_path(vault_path: str, allowed_root: str | None = None) -> Path:
    """
    Validate and resolve vault path with Path Traversal protection.

    Ensures the resolved path is within the allowed root directory.
    Uses Path.relative_to() for robust boundary checking.
    Raises ValueError if the path escapes the allowed boundary.
    """
    resolved = Path(vault_path).resolve()

    if allowed_root:
        allowed = Path(allowed_root).resolve()
        try:
            resolved.relative_to(allowed)
        except ValueError:
            raise ValueError(
                f"Path traversal detected: '{vault_path}' resolves outside allowed root '{allowed}'"
            ) from None

    if not resolved.exists():
        raise FileNotFoundError(f"Vault path does not exist: {resolved}")

    if not resolved.is_dir():
        raise NotADirectoryError(f"Vault path is not a directory: {resolved}")

    return resolved


def resolve_vault_path(
    arguments: dict[str, Any],
    env_var: str = "POWER_VAULT_DIR",
    fallback: str | None = None,
) -> Path:
    """
    Resolve vault path from MCP arguments, environment variable, or fallback.

    Applies Path Traversal validation for all resolved paths.
    """
    explicit = arguments.get("vault_path")
    if explicit:
        return validate_vault_path(explicit)

    env_val = os.getenv(env_var)
    if env_val:
        return validate_vault_path(env_val)

    cwd = fallback if fallback else os.getcwd()
    return Path(cwd).resolve()


def atomic_write(filepath: Path, content: str, encoding: str = "utf-8") -> None:
    """
    Write content to file atomically using temp file + rename.

    Prevents corruption from interrupted writes (0-byte files).
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(filepath.parent),
        prefix=f".{filepath.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
        os.replace(tmp_path, filepath)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def create_backup(filepath: Path, backup_dir: Path | None = None) -> Path | None:
    """
    Create a timestamped backup of a file before modification.

    Returns the backup path, or None if the source doesn't exist.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return None

    if backup_dir is None:
        backup_dir = filepath.parent / ".backups"

    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_name = f"{filepath.stem}.{timestamp}{filepath.suffix}"
    backup_path = backup_dir / backup_name

    shutil.copy2(filepath, backup_path)
    return backup_path


def clean_note_name(filename: str) -> str:
    """Remove .md extension and normalize to lowercase for comparison."""
    return filename.replace(".md", "").strip().lower()


def get_relative_path(filepath: Path, base_dir: Path) -> str:
    """Get relative path from base directory."""
    return os.path.relpath(filepath, base_dir)


def is_excluded_dir(dirname: str) -> bool:
    """Check if directory should be excluded from scanning."""
    return dirname in EXCLUDED_DIRS


def is_excluded_orphan(filename: str, rel_path: str) -> bool:
    """Check if file should be excluded from orphan detection."""
    return filename in EXCLUDED_ORPHAN_FILES or rel_path.startswith("06_Daily_Logs/")


def load_powerignore(vault_dir: Path) -> Any:
    """Load the optional `.powerignore` file (gitignore syntax) from the vault root.

    Returns a compiled ``pathspec.PathSpec`` instance, or ``None`` when the file is
    absent or ``pathspec`` is unavailable. Patterns are matched against POSIX-style
    relative paths so that vendored trees (``node_modules/``, ``.venv/``, ``.claude/``)
    can be excluded from OKF metadata / lint scanning without editing source code.
    """
    if not _HAS_PATHSPEC:
        return None
    ignore_file = vault_dir / POWERIGNORE_FILE
    if not ignore_file.is_file():
        return None
    try:
        lines = ignore_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def is_path_ignored(rel_path: str, spec: Any) -> bool:
    """Return True if ``rel_path`` (POSIX-style) matches the given ignore spec."""
    if spec is None:
        return False
    posix = rel_path.replace(os.sep, "/")
    return bool(spec.match_file(posix))


# Top-level folders that constitute the OKF knowledge base. Files outside this
# scope (e.g. the ``projects/`` tree of foreign source repositories, vendor dirs)
# are never subject to OKF metadata / lint requirements.
OKF_SCOPE_FOLDERS = frozenset(PARA_FOLDERS_) | {"brain"}


def is_in_okf_scope(rel_path: str) -> bool:
    """Return True if a note lives inside the OKF knowledge base.

    Scope = a PARA folder (``00_Inbox`` .. ``06_Daily_Logs``) or the ``brain/``
    subtree, plus root-level daily-log notes (``2026-*.md``) and the vault's
    system index files (``index.md`` / ``log.md`` / ``_index.md``). Everything
    else (foreign repos under ``projects/``, tool config, repo meta files such
    as ``GEMINI.md`` / ``LACA.md``) is intentionally outside OKF and must not
    raise metadata warnings.
    """
    parts = Path(rel_path).parts
    if len(parts) == 1:
        name = parts[0]
        return name.startswith("2026-") or name in {"index.md", "log.md", "_index.md"}
    return parts[0] in OKF_SCOPE_FOLDERS


class RateLimiter:
    """Simple sliding-window rate limiter per key."""

    def __init__(self, max_calls: int = 10, period: float = 60.0):
        self.max_calls = max_calls
        self.period = period
        self._windows: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        window = self._windows[key]
        cutoff = now - self.period
        self._windows[key] = [ts for ts in window if ts > cutoff]
        if len(self._windows[key]) >= self.max_calls:
            return False
        self._windows[key].append(now)
        return True

    def remaining(self, key: str) -> int:
        now = time.monotonic()
        window = self._windows.get(key, [])
        cutoff = now - self.period
        active = sum(1 for ts in window if ts > cutoff)
        return max(0, self.max_calls - active)


def get_cache_dir() -> Path:
    """Return the cache directory for power-framework (XDG-compliant)."""
    cache_home = os.getenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    cache_dir = Path(cache_home) / "power-framework"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def validate_path_in_vault(filepath: Path, vault_dir: Path) -> Path:
    """Validate that a file path is within the vault directory (path traversal protection).

    Raises ValueError if the path escapes the vault boundary.
    """
    resolved_file = filepath.resolve()
    resolved_vault = vault_dir.resolve()
    try:
        resolved_file.relative_to(resolved_vault)
    except ValueError:
        raise ValueError(
            f"Path traversal detected: '{filepath}' is outside the vault '{vault_dir}'"
        ) from None
    return resolved_file


try:
    from importlib.metadata import version as _get_version

    __version__ = _get_version("power-framework")
except Exception:
    __version__ = "1.8.0"

"""
P.O.W.E.R. Utility Functions.

Path validation, atomic writes, backup management, and security helpers.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def validate_vault_path(vault_path: str, allowed_root: str | None = None) -> Path:
    """
    Validate and resolve vault path with Path Traversal protection.

    Ensures the resolved path is within the allowed root directory.
    Raises ValueError if the path escapes the allowed boundary.
    """
    resolved = Path(vault_path).resolve()

    if allowed_root:
        allowed = Path(allowed_root).resolve()
        if not str(resolved).startswith(str(allowed)):
            raise ValueError(
                f"Path traversal detected: '{vault_path}' resolves outside allowed root '{allowed}'"
            )

    if not resolved.exists():
        raise FileNotFoundError(f"Vault path does not exist: {resolved}")

    if not resolved.is_dir():
        raise NotADirectoryError(f"Vault path is not a directory: {resolved}")

    return resolved


def resolve_vault_path(
    arguments: dict,
    env_var: str = "POWER_VAULT_DIR",
    fallback: str | None = None,
) -> Path:
    """
    Resolve vault path from MCP arguments, environment variable, or fallback.

    Applies Path Traversal validation when an explicit path is provided.
    """
    explicit = arguments.get("vault_path")
    if explicit:
        return validate_vault_path(explicit)

    env_val = os.getenv(env_var)
    if env_val:
        return Path(env_val).resolve()

    if fallback:
        return Path(fallback).resolve()

    return Path(os.getcwd()).resolve()


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


EXCLUDED_DIRS = frozenset({".git", "05_Templates", "scratch", ".system_generated", ".agents"})


def is_excluded_dir(dirname: str) -> bool:
    """Check if directory should be excluded from scanning."""
    return dirname in EXCLUDED_DIRS


EXCLUDED_ORPHAN_FILES = frozenset(
    {
        "README.md",
        "Home.md",
        "index.md",
        "log.md",
        "Successor-Hub.md",
        "PARA-OKF-LLM_Wiki.md",
        "Weby_PARA-OKF-LLM_Wiki.md",
    }
)


def is_excluded_orphan(filename: str, rel_path: str) -> bool:
    """Check if file should be excluded from orphan detection."""
    return filename in EXCLUDED_ORPHAN_FILES or rel_path.startswith("06_Daily_Logs/")


__version__ = "1.4.0"

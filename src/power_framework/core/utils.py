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

from .constants import EXCLUDED_DIRS, EXCLUDED_ORPHAN_FILES


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

    env_val = os.getenv(env_var) or os.getenv("POWER_VAULT_PATH")
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


# Performance Plan §2: pin the fastembed model weight cache to a stable,
# persistent location (NOT /tmp) so embedding model files are downloaded once
# and reused across runs/sessions instead of being re-fetched on every cold
# start.
def get_embedding_cache_dir() -> Path:
    """Return a persistent cache dir for embedding model weights."""
    cache_dir = get_cache_dir() / "embeddings"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


# Ensure fastembed (and qwen3-embed) use the persistent cache dir.
os.environ.setdefault("FASTEMBED_CACHE_DIR", str(get_embedding_cache_dir()))


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
    __version__ = "2.2.3"


def run_opencode_cli(prompt: str) -> str:
    """Run local OpenCode agent CLI tool to get LLM completion."""
    import logging
    import subprocess

    local_logger = logging.getLogger(__name__)

    # Locate opencode binary
    binary = "/root/.opencode/bin/opencode"
    if not os.path.exists(binary):
        binary = shutil.which("opencode") or "opencode"

    try:
        res = subprocess.run(  # noqa: S603
            [binary, "run", prompt, "--auto"],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        stdout = res.stdout
        lines = stdout.splitlines()
        content_lines = []
        started = False
        for line in lines:
            if started:
                content_lines.append(line)
            elif line.strip().startswith("> "):
                started = True
            elif not line.strip():
                continue
            else:
                pass

        if not started:
            return stdout.strip()

        return "\n".join(content_lines).strip()
    except Exception as e:
        local_logger.warning("Failed to run local opencode CLI: %s", e)
        return ""

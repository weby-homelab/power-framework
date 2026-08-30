"""
P.O.W.E.R. Utility Functions.

Path validation, atomic writes, backup management, and security helpers.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import tempfile
import time
from collections import defaultdict
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.parse import unquote

from .constants import EXCLUDED_DIRS, EXCLUDED_ORPHAN_FILES, is_catalog_filename

_BACKUP_NAME_RE = re.compile(r"^.+\.\d{8}_\d{6}(?:_\d+)?\.[^.]+$")


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

    ``newline=""`` disables newline translation so the file on disk is exactly
    ``content.encode(encoding)`` on every platform. Without it, text mode maps
    each "\\n" to ``os.linesep``, and on Windows a caller that bounded its
    content by byte length -- such as the INDEX_MAX_BYTES catalog contract --
    writes an artifact larger than the bound it just enforced, by one byte per
    line.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(filepath.parent),
        prefix=f".{filepath.name}.",
        suffix=".tmp",
    )
    try:
        file_obj = os.fdopen(fd, "w", encoding=encoding, newline="")
        fd = -1
        with file_obj as f:
            f.write(content)
        os.replace(tmp_path, filepath)
    except Exception:
        if fd >= 0:
            os.close(fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def resolve_path_in_vault(
    vault_root: Path,
    untrusted_relative_path: str,
    allowed_directories: tuple[str, ...] | None = None,
) -> Path:
    """Resolve a Markdown file path without allowing it to escape a vault root.

    The supplied path is intentionally treated as untrusted input: absolute and
    Windows-drive paths, traversal components, control characters, backslashes,
    non-Markdown targets, and symlink escapes are rejected.  The parent must
    already exist so callers do not create an attacker-selected directory tree.
    """
    root = validate_vault_path(str(vault_root))
    raw_path = str(untrusted_relative_path)
    decoded_path = unquote(raw_path)

    if not raw_path or any(ord(char) < 32 or ord(char) == 127 for char in decoded_path):
        raise ValueError("Invalid vault-relative path")
    windows_path = PureWindowsPath(decoded_path)
    posix_path = Path(decoded_path)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError("Absolute paths are not allowed")
    if "\\" in decoded_path:
        raise ValueError("Windows path separators are not allowed")

    path_parts = Path(decoded_path).parts
    if not path_parts or any(part in {".", ".."} for part in path_parts):
        raise ValueError("Path traversal is not allowed")
    if allowed_directories and path_parts[0] not in allowed_directories:
        raise ValueError("Path is outside the allowed vault directories")
    if Path(path_parts[-1]).suffix.lower() != ".md":
        raise ValueError("Only Markdown note targets are allowed")

    candidate = root.joinpath(*path_parts)
    try:
        parent = candidate.parent.resolve(strict=True)
        parent.relative_to(root)
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError("Target parent is outside the vault or does not exist") from exc

    target = parent / candidate.name
    if target.is_symlink():
        raise ValueError("Symlink note targets are not allowed")
    return target


def atomic_write_in_vault(
    vault_root: Path,
    untrusted_relative_path: str,
    content: str,
    encoding: str = "utf-8",
    allowed_directories: tuple[str, ...] | None = None,
) -> Path:
    """Atomically write an untrusted relative note path inside a vault.

    The destination directory is opened with ``O_NOFOLLOW`` and every temporary
    file operation is performed through that directory descriptor. This keeps a
    symlink replacement from redirecting the write outside the canonical root.
    """
    target = resolve_path_in_vault(vault_root, untrusted_relative_path, allowed_directories)

    if os.name == "nt":  # pragma: no cover - exercised on Windows
        # Windows does not implement ``dir_fd`` or ``O_NOFOLLOW``. Keep the
        # same atomic temp-file contract with a directory-local tempfile, and
        # recheck the destination immediately before replacement to reject a
        # symlink swap where the platform exposes one.
        fd, temporary_path = tempfile.mkstemp(
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding=encoding) as temporary_file:
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            if target.is_symlink():
                raise ValueError("Symlink note targets are not allowed")
            os.replace(temporary_path, target)
        except Exception:
            with suppress(FileNotFoundError):
                os.unlink(temporary_path)
            raise
        return target

    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(target.parent, directory_flags)
    temporary_name = f".{target.name}.{secrets.token_hex(16)}.tmp"
    temporary_fd: int | None = None

    try:
        temporary_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        temporary_fd = os.open(temporary_name, temporary_flags, 0o600, dir_fd=directory_fd)
        with os.fdopen(temporary_fd, "w", encoding=encoding) as temporary_file:
            temporary_fd = None
            temporary_file.write(content)
        os.replace(
            temporary_name,
            target.name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
    except Exception:
        if temporary_fd is not None:
            os.close(temporary_fd)
        with suppress(FileNotFoundError):
            os.unlink(temporary_name, dir_fd=directory_fd)
        raise
    finally:
        os.close(directory_fd)

    return target


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

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{filepath.stem}.{timestamp}{filepath.suffix}"
    counter = 1
    while backup_path.exists():
        backup_path = backup_dir / f"{filepath.stem}.{timestamp}_{counter}{filepath.suffix}"
        counter += 1

    shutil.copy2(filepath, backup_path)
    return backup_path


def _backup_files(backup_dir: Path) -> list[Path]:
    """Return only files using POWER's timestamped backup naming contract."""
    if not backup_dir.is_dir():
        return []
    return sorted(
        (
            path
            for path in backup_dir.iterdir()
            if path.is_file() and not path.is_symlink() and _BACKUP_NAME_RE.match(path.name)
        ),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )


def prune_backups(
    backup_dir: Path,
    *,
    max_count: int | None = 50,
    max_age_days: float | None = 30,
    max_bytes: int | None = 500 * 1024 * 1024,
    dry_run: bool = True,
) -> list[Path]:
    """Preview or remove timestamped backups outside explicit retention limits.

    The default is a dry run. Only files created by :func:`create_backup` are
    eligible; unrelated files and symlinks are never removed.
    """
    for name, value in (
        ("max_count", max_count),
        ("max_age_days", max_age_days),
        ("max_bytes", max_bytes),
    ):
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative or None")

    candidates = _backup_files(Path(backup_dir))
    remove: set[Path] = set()
    if max_count is not None:
        remove.update(candidates[max_count:])

    if max_age_days is not None:
        cutoff = datetime.now(UTC).timestamp() - timedelta(days=max_age_days).total_seconds()
        remove.update(path for path in candidates if path.stat().st_mtime < cutoff)

    if max_bytes is not None:
        retained_bytes = 0
        for path in candidates:
            size = path.stat().st_size
            if path in remove:
                continue
            if retained_bytes + size > max_bytes:
                remove.add(path)
            else:
                retained_bytes += size

    selected = [path for path in candidates if path in remove]
    if not dry_run:
        for path in selected:
            path.unlink()
    return selected


def restore_backup(backup_path: Path, destination: Path, *, overwrite: bool = False) -> Path:
    """Atomically restore one backup, requiring explicit overwrite permission."""
    source = Path(backup_path)
    target = Path(destination)
    if not source.is_file() or source.is_symlink():
        raise FileNotFoundError(f"Backup is not a regular file: {source}")
    if source.resolve() == target.resolve():
        raise ValueError("Backup and destination must be different paths")
    if target.exists() and not overwrite:
        raise FileExistsError(f"Destination already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError("Symlink destinations are not allowed")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".restore.tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
        shutil.copy2(source, temporary_path)
        os.replace(temporary_path, target)
    except Exception:
        if temporary_path is not None:
            with suppress(FileNotFoundError):
                temporary_path.unlink()
        raise
    return target


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
    normalized_rel_path = rel_path.replace("\\", "/")
    normalized_filename = normalized_rel_path.rsplit("/", 1)[-1]
    is_root_daily_log = "/" not in normalized_rel_path and bool(
        re.match(r"^\d{4}-\d{2}-\d{2}_.*\.md$", normalized_filename)
    )
    return (
        filename in EXCLUDED_ORPHAN_FILES
        or normalized_filename in EXCLUDED_ORPHAN_FILES
        or is_catalog_filename(normalized_filename)
        or normalized_rel_path.startswith(("04_Archive/", "06_Daily_Logs/"))
        or is_root_daily_log
    )


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


def get_cache_dir(*, create: bool = True) -> Path:
    """Return the cache directory, optionally without creating it."""
    cache_home = os.getenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    cache_dir = Path(cache_home) / "power-framework"
    if create:
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


# Ensure fastembed (and qwen3-embed) use the persistent cache dir without
# creating it during a read-only import. The directory is created only when a
# model-backed operation explicitly asks for ``get_embedding_cache_dir()``.
os.environ.setdefault("FASTEMBED_CACHE_DIR", str(get_cache_dir(create=False) / "embeddings"))


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


def get_cpu_worker_limit(max_cap: int | None = None) -> int:
    """Calculate strict CPU worker limit ensuring POWER never exceeds 50% CPU capacity.

    Formula: max(1, (os.cpu_count() or 4) // 2)
    If max_cap is provided, returns min(max_cap, cpu_limit).
    """
    cpu_count = os.cpu_count() or 4
    limit = max(1, cpu_count // 2)
    if max_cap is not None:
        return max(1, min(max_cap, limit))
    return limit


def enforce_cpu_throttling_env() -> None:
    """Strict 50% CPU Throttling Mandate.

    Enforces environment variables for underlying native libraries (OpenMP, BLAS, MKL, ONNX, etc.)
    so that thread pools never exceed 50% of available CPU cores.
    """
    cpu_limit_str = str(get_cpu_worker_limit())
    env_vars = (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "POWER_EMBED_NUM_THREADS",
    )
    for var in env_vars:
        val = os.getenv(var)
        if val is None:
            os.environ[var] = cpu_limit_str
        else:
            try:
                parsed = int(val)
                limit_int = int(cpu_limit_str)
                if parsed > limit_int:
                    os.environ[var] = cpu_limit_str
            except ValueError:
                os.environ[var] = cpu_limit_str


try:
    from importlib.metadata import version as _get_version

    __version__ = _get_version("power-framework")
except Exception:
    __version__ = "3.7.9"


def run_opencode_cli(prompt: str) -> str:
    """Run local OpenCode agent CLI tool to get LLM completion."""
    import logging
    import subprocess

    local_logger = logging.getLogger(__name__)

    # Locate opencode binary dynamically across systems
    user_opencode = Path.home() / ".opencode" / "bin" / "opencode"
    if user_opencode.exists():
        binary = str(user_opencode)
    else:
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

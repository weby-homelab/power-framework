"""Per-vault mutation coordination for CLI, MCP, and library callers.

Mutations are serialized only within one vault.  The in-process lock protects
threads in the current Python process; the advisory file lock protects other
POWER processes that operate on the same vault.  Different vaults retain
parallelism because their lock objects and lock files are independent.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

try:  # POSIX advisory locks.
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None  # type: ignore[assignment]

try:  # Windows byte-range locks.
    import msvcrt
except ImportError:  # pragma: no cover - exercised on POSIX
    msvcrt = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_registry_guard = threading.Lock()
_vault_locks: dict[Path, threading.RLock] = {}
_compatibility_lock = threading.RLock()


def _lock_descriptor(descriptor: int) -> None:
    """Acquire an exclusive advisory lock on one byte of the lock file."""
    if fcntl is not None:
        flock = getattr(fcntl, "flock")  # noqa: B009 - optional POSIX module.
        lock_ex = getattr(fcntl, "LOCK_EX")  # noqa: B009 - optional POSIX module.
        flock(descriptor, lock_ex)
        return
    if msvcrt is not None:  # pragma: no cover - Windows-only branch
        # ``msvcrt.locking`` locks bytes, so make the lock file non-empty
        # before seeking and taking the one-byte region.
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        return
    raise OSError("no supported platform file-lock implementation")


def _unlock_descriptor(descriptor: int) -> None:
    """Release a lock acquired by :func:`_lock_descriptor`."""
    if fcntl is not None:
        flock = getattr(fcntl, "flock")  # noqa: B009 - optional POSIX module.
        lock_un = getattr(fcntl, "LOCK_UN")  # noqa: B009 - optional POSIX module.
        flock(descriptor, lock_un)
        return
    if msvcrt is not None:  # pragma: no cover - Windows-only branch
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)


def _get_vault_lock(vault_dir: Path) -> threading.RLock:
    """Return the stable in-process lock for one canonical vault path."""
    root = Path(vault_dir).expanduser().resolve()
    with _registry_guard:
        return _vault_locks.setdefault(root, threading.RLock())


@contextlib.contextmanager
def vault_mutation(vault_dir: Path) -> Iterator[Path]:
    """Hold the same-vault in-process and cross-process mutation locks."""
    root = Path(vault_dir).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Vault path is not a directory: {root}")

    lock_path = root / ".power" / "mutation.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    process_lock = _get_vault_lock(root)
    with process_lock:
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            _lock_descriptor(descriptor)
            yield root
        finally:
            with contextlib.suppress(OSError):
                _unlock_descriptor(descriptor)
            os.close(descriptor)


def execute_vault_mutation[T](vault_dir: Path, operation: Callable[[], T]) -> T:
    """Execute one synchronous operation under the canonical vault boundary."""
    with vault_mutation(vault_dir):
        return operation()


async def run_blocking[T](sync_fn: Callable[[], T]) -> T:
    """Run a blocking operation and join its executor before returning.

    Polling the submitted future avoids a Python 3.13 runtime deadlock seen
    when ``asyncio`` waits for an executor callback after file-backed work.
    The work still runs in the bounded executor; only completion observation is
    kept on the event loop.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(sync_fn)
        while not future.done():
            await asyncio.sleep(0.01)
        return future.result()


async def run_vault_mutation[T](vault_dir: Path, operation: Callable[[], T]) -> T:
    """Run a synchronous mutation under per-vault locks without blocking asyncio."""
    return await run_blocking(lambda: execute_vault_mutation(vault_dir, operation))


async def enqueue_compatibility_write[T](sync_fn: Callable[[], T]) -> T:
    """Preserve the legacy queue API for callers without a vault argument.

    Production CLI/MCP paths use :func:`run_vault_mutation`; this fallback is
    intentionally process-local and has no worker task or active-vault state.
    """
    return await run_blocking(lambda: _run_compatibility_write(sync_fn))


def _run_compatibility_write[T](sync_fn: Callable[[], T]) -> T:
    with _compatibility_lock:
        return sync_fn()


def reset_mutation_registry_for_test() -> None:
    """Clear lock objects between isolated test processes."""
    with _registry_guard:
        _vault_locks.clear()

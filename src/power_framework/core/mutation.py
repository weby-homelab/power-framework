"""Per-vault mutation coordination for CLI, MCP, and library callers.

Mutations are serialized only within one vault.  The in-process lock protects
threads in the current Python process; the advisory file lock protects other
POWER processes that operate on the same vault.  Different vaults retain
parallelism because their lock objects and lock files are independent.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

T = TypeVar("T")

_registry_guard = threading.Lock()
_vault_locks: dict[Path, threading.RLock] = {}
_compatibility_lock = threading.RLock()


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
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield root
        finally:
            with contextlib.suppress(OSError):
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def execute_vault_mutation(vault_dir: Path, operation: Callable[[], T]) -> T:
    """Execute one synchronous operation under the canonical vault boundary."""
    with vault_mutation(vault_dir):
        return operation()


async def run_blocking(sync_fn: Callable[[], T]) -> T:
    """Run a blocking operation and join its executor before returning."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(executor, sync_fn)


async def run_vault_mutation(vault_dir: Path, operation: Callable[[], T]) -> T:
    """Run a synchronous mutation under per-vault locks without blocking asyncio."""
    return await run_blocking(lambda: execute_vault_mutation(vault_dir, operation))


async def enqueue_compatibility_write(sync_fn: Callable[[], T]) -> T:
    """Preserve the legacy queue API for callers without a vault argument.

    Production CLI/MCP paths use :func:`run_vault_mutation`; this fallback is
    intentionally process-local and has no worker task or active-vault state.
    """
    return await run_blocking(lambda: _run_compatibility_write(sync_fn))


def _run_compatibility_write(sync_fn: Callable[[], T]) -> T:
    with _compatibility_lock:
        return sync_fn()


def reset_mutation_registry_for_test() -> None:
    """Clear lock objects between isolated test processes."""
    with _registry_guard:
        _vault_locks.clear()

"""Backward-compatible aliases for the pre-3.3 mutation API.

The old implementation owned a process-wide asyncio worker.  It has been
replaced by explicit per-vault mutation boundaries in ``core.mutation``;
keeping these aliases avoids an unnecessary public API break for integrations
that used ``run_blocking`` or ``enqueue_write`` directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .mutation import enqueue_compatibility_write, run_blocking

if TYPE_CHECKING:
    from collections.abc import Callable


async def enqueue_write[T](sync_fn: Callable[[], T]) -> T:
    """Run a legacy write call without creating a background worker task."""
    return await enqueue_compatibility_write(sync_fn)


async def drain() -> None:
    """Compatibility no-op; writes are joined before their await returns."""


def reset_for_test() -> None:
    """Compatibility no-op retained for older test and integration callers."""


__all__ = ["drain", "enqueue_write", "reset_for_test", "run_blocking"]

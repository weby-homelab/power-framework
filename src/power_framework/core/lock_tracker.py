"""Strict 3-level lock acquisition hierarchy tracker (ADR-PSE-007).

Enforces:
- Level 1: Vault Mutation Lock (.power/mutation.lock)
- Level 2: TaskStore Process Lock (.power/tasks/.lock)
- Level 3: PSE Project Process Lock (.power/projects/<project_id>/.lock)
- Ascending acquisition order only (Level 1 -> Level 2 -> Level 3).
- Re-entrancy at the same level is permitted.
- Out-of-order acquisition raises LockHierarchyViolationError.
"""

from __future__ import annotations

import contextlib
import threading
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Iterator

LEVEL_MUTATION: int = 1
LEVEL_TASK: int = 2
LEVEL_PROJECT: int = 3


class LockHierarchyViolationError(RuntimeError):
    """Raised when locks are acquired out of ascending hierarchical order."""


class LockHierarchyTracker:
    """Thread-local tracker for the strict 3-level lock acquisition hierarchy."""

    LEVEL_MUTATION: int = LEVEL_MUTATION
    LEVEL_TASK: int = LEVEL_TASK
    LEVEL_PROJECT: int = LEVEL_PROJECT

    _local = threading.local()

    @classmethod
    def get_held_levels(cls) -> list[int]:
        if not hasattr(cls._local, "levels"):
            cls._local.levels = []
        return cast("list[int]", cls._local.levels)

    @classmethod
    def push_level(cls, level: int) -> None:
        held = cls.get_held_levels()
        if held and max(held) > level:
            raise LockHierarchyViolationError(
                f"Lock hierarchy violation: cannot acquire Level {level} while holding Level {max(held)}. "
                "Locks must strictly be acquired in ascending order (Level 1: Mutation -> Level 2: Task -> Level 3: Project)."
            )
        held.append(level)

    @classmethod
    def pop_level(cls, level: int) -> None:
        held = cls.get_held_levels()
        if held and held[-1] == level:
            held.pop()
        elif level in held:
            held.remove(level)

    @classmethod
    @contextlib.contextmanager
    def hold_level(cls, level: int) -> Iterator[None]:
        cls.push_level(level)
        try:
            yield
        finally:
            cls.pop_level(level)


@contextlib.contextmanager
def hold_level(level: int) -> Iterator[None]:
    """Convenience context manager for LockHierarchyTracker.hold_level."""
    with LockHierarchyTracker.hold_level(level):
        yield

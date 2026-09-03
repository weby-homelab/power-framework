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
    def get_held_projects(cls) -> list[str | None]:
        if not hasattr(cls._local, "projects"):
            cls._local.projects = []
        return cast("list[str | None]", cls._local.projects)

    @classmethod
    def get_current_project_id(cls) -> str | None:
        held_projs = cls.get_held_projects()
        active_pids = [p for p in held_projs if p is not None]
        return active_pids[-1] if active_pids else None

    @classmethod
    def push_level(cls, level: int, project_id: str | None = None) -> None:
        held = cls.get_held_levels()
        if held and max(held) > level:
            raise LockHierarchyViolationError(
                f"Lock hierarchy violation: cannot acquire Level {level} while holding Level {max(held)}. "
                "Locks must strictly be acquired in ascending order (Level 1: Mutation -> Level 2: Task -> Level 3: Project)."
            )
        if level == cls.LEVEL_PROJECT:
            held_projs = cls.get_held_projects()
            active_pids = [p for p in held_projs if p is not None]
            if active_pids and project_id is not None and active_pids[-1] != project_id:
                raise LockHierarchyViolationError(
                    f"Lock hierarchy violation: cannot acquire Level 3 project lock for '{project_id}' "
                    f"while holding Level 3 project lock for '{active_pids[-1]}'. "
                    "Cross-project nested locks are forbidden to prevent deadlock."
                )
            held_projs.append(project_id)
        held.append(level)

    @classmethod
    def pop_level(cls, level: int) -> None:
        held = cls.get_held_levels()
        if held and held[-1] == level:
            held.pop()
        elif level in held:
            held.remove(level)
        if level == cls.LEVEL_PROJECT:
            held_projs = cls.get_held_projects()
            if held_projs:
                held_projs.pop()

    @classmethod
    @contextlib.contextmanager
    def hold_level(cls, level: int, project_id: str | None = None) -> Iterator[None]:
        cls.push_level(level, project_id=project_id)
        try:
            yield
        finally:
            cls.pop_level(level)


@contextlib.contextmanager
def hold_level(level: int, project_id: str | None = None) -> Iterator[None]:
    """Convenience context manager for LockHierarchyTracker.hold_level."""
    with LockHierarchyTracker.hold_level(level, project_id=project_id):
        yield

"""Deterministic fault-injection harness for crash-recovery testing (Phase C).

This module provides a process-wide, opt-in fault injector. It is **disabled by
default** and has zero effect on production code paths. Tests arm a named crash
point and the next matching operation raises ``InjectedFault`` *before* it
commits its postimages -- deterministically reproducing the hard-kill scenarios
that :class:`~power_framework.core.task_store.TaskStore`'s transaction manifest
recovers from.

    Usage in a test::

        from power_framework.core.fault_injection import fault_injector, InjectedFaultError

        fault_injector.arm("task.prepare_after_manifest")
        try:
            store.save_task(task, event=ev)   # simulates SIGKILL after manifest
        except InjectedFaultError:
            pass
        # ... inspect orphaned prepared manifest, then:
        store.recover()                        # verify rollback
"""

from __future__ import annotations

__all__ = ["FaultInjector", "InjectedFaultError", "fault_injector"]


class InjectedFaultError(Exception):
    """Raised at a deterministic crash point to simulate a hard process kill."""

    def __init__(self, point: str) -> None:
        super().__init__(f"injected fault at crash point: {point}")
        self.point = point


class FaultInjector:
    """A tiny deterministic hook registry keyed by named crash point.

    Each armed point carries a remaining counter so a fault can be scheduled
    exactly ``N`` times (default once). Decrement happens at raise time.
    """

    def __init__(self) -> None:
        self._armed: dict[str, int] = {}

    def arm(self, point: str, times: int = 1) -> None:
        """Schedule ``times`` faults at ``point`` (default: once)."""
        if times < 1:
            raise ValueError("times must be >= 1")
        self._armed[point] = self._armed.get(point, 0) + times

    def disarm(self, point: str | None = None) -> None:
        """Clear ``point`` (or all points when ``None``)."""
        if point is None:
            self._armed.clear()
        else:
            self._armed.pop(point, None)

    def is_armed(self, point: str) -> bool:
        return self._armed.get(point, 0) > 0

    def maybe_raise(self, point: str) -> None:
        """Raise :class:`InjectedFault` if ``point`` is armed; else no-op."""
        if self._armed.get(point, 0) > 0:
            self._armed[point] -= 1
            raise InjectedFaultError(point)

    def reset(self) -> None:
        """Disarm everything (convenience for test teardown)."""
        self._armed.clear()


# Process-wide singleton. Safe because it is inert unless explicitly armed.
fault_injector = FaultInjector()

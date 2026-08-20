"""Stable domain error types shared by POWER transport adapters."""

from __future__ import annotations


class ConflictError(ValueError, RuntimeError):
    """A request conflicts with the current durable domain state."""

    code = "conflict"
    status_code = 409


__all__ = ["ConflictError"]

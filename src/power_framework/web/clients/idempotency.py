"""Deterministic idempotency-key derivation for Web UI mutations.

Two identical logical requests (e.g. a double-clicked form) must produce the
same key so the POWER core can replay the prior result instead of raising a
duplicate error. Different requests must produce different keys.
"""

from __future__ import annotations

import hashlib

_PREFIX = "web"


def key_for(action: str, **fields: object) -> str:
    """Return a stable idempotency key for a normalized set of request fields."""
    canonical = "|".join(f"{k}={fields[k]}" for k in sorted(fields))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"{_PREFIX}:{action}:{digest}"


__all__ = ["key_for"]

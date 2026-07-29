"""Central fail-closed policy for sending vault-derived data off-host."""

from __future__ import annotations

import os
from enum import IntEnum, StrEnum
from urllib.parse import urlparse

from .models import Sensitivity


class EgressOperation(StrEnum):
    """Every POWER path that can contact a non-local service."""

    EMBEDDINGS = "embeddings"
    RERANKING = "reranking"
    QUERY_EXPANSION = "query_expansion"
    ROT = "rot"


class EgressDeniedError(PermissionError):
    """Raised before sensitive vault content can leave the local host."""


class _PolicyLevel(IntEnum):
    DENY = 0
    PUBLIC = 1
    INTERNAL = 2
    SENSITIVE = 3


_LEVELS = {
    "deny": _PolicyLevel.DENY,
    "allow-public": _PolicyLevel.PUBLIC,
    "allow-internal": _PolicyLevel.INTERNAL,
    "allow-sensitive": _PolicyLevel.SENSITIVE,
}
_SENSITIVITY_LEVELS = {
    Sensitivity.PUBLIC.value: _PolicyLevel.PUBLIC,
    Sensitivity.INTERNAL.value: _PolicyLevel.INTERNAL,
    Sensitivity.SENSITIVE.value: _PolicyLevel.SENSITIVE,
}


def configured_egress_policy() -> str:
    """Return the explicit policy name; absent configuration always denies."""
    return os.getenv("POWER_EGRESS_POLICY", "deny").lower()


def require_remote_egress(operation: EgressOperation, sensitivity: str = "internal") -> None:
    """Permit a remote call only under a policy explicit enough for its data."""
    policy = configured_egress_policy()
    allowed = _LEVELS.get(policy)
    level = _SENSITIVITY_LEVELS.get(sensitivity.lower())
    if allowed is None:
        raise EgressDeniedError(
            "POWER_EGRESS_POLICY must be deny, allow-public, allow-internal, or allow-sensitive"
        )
    if level is None:
        raise EgressDeniedError(f"Unknown sensitivity '{sensitivity}' for {operation.value}")
    if allowed < level:
        raise EgressDeniedError(
            f"remote {operation.value} denied for {sensitivity} content by POWER_EGRESS_POLICY={policy}"
        )


def is_remote_endpoint(url: str) -> bool:
    """Treat only non-loopback HTTP endpoints as remote content egress."""
    host = urlparse(url).hostname
    return bool(host and host not in {"localhost", "127.0.0.1", "::1"})
